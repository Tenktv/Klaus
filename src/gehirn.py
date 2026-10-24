"""
Klaus - Gehirn und Gedaechtnis

Gedaechtnis: Fakten, die Klaus sich merken soll ("Klaus, merk dir ..."), in
data/gedaechtnis.json. Sie stehen in jedem System-Prompt - lokal wie bei Claude.

Claude-Gehirn: schwierige Fragen gehen ueber Claude Code (`claude -p`) an Claude.
Dieser Claude hat deine Skills/Plugins, darf im Web suchen und behaelt das
Gespraech (gleiche Sitzung), solange ihr innerhalb von 3 Minuten weiterredet.

.env (optional):
    KLAUS_GEHIRN          auto (Standard) | claude | lokal
    KLAUS_CLAUDE_MODELL   opus (Standard) | sonnet | ...
"""

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import threading
import time
import zlib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
GEDAECHTNIS_PATH = BASE_DIR / "data" / "gedaechtnis.json"  # alt, wird einmalig in den Vault uebernommen
# Obsidian-Vault: normale Markdown-Notizen, in Obsidian les- und bearbeitbar
VAULT = Path(os.getenv("KLAUS_VAULT", "").strip() or Path.home() / "Documents" / "Klaus Gedächtnis")
FAKTEN_PATH = VAULT / "Nikola.md"
PROTOKOLL = os.getenv("KLAUS_PROTOKOLL", "1").strip() != "0"  # Gespraeche als Tagesnotiz mitschreiben
ARBEITSORDNER = BASE_DIR / "data" / "gehirn"
MODUS = os.getenv("KLAUS_GEHIRN", "auto").strip().lower()
MODELL = os.getenv("KLAUS_CLAUDE_MODELL", "opus").strip()
NAME = os.getenv("KLESRO_ABSENDER_NAME", "Nikola Georgiev")
SITZUNG_VERGESSEN_SEK = 180

_sperre = threading.Lock()

# Wie Klaus denkt und spricht. Gilt fuer Claude und (gekuerzt) fuer das lokale Modell.
PERSONA = f"""Du bist Klaus, der persoenliche Sprach-Assistent von {NAME}. {NAME.split()[0]} betreibt
Klesro Web, ein kleines Webdesign-Studio im Raum Goeppingen, programmiert viel und spielt gern
(CS2, TFT, League). Ihr kennt euch - stell dich nicht vor und begruesse nicht, ausser er gruesst.

Wie du denkst:
- Erst verstehen, was er wirklich will. Ist eine Bitte mehrdeutig und die Antwort haengt davon ab,
  stell genau eine kurze Rueckfrage, statt zu raten.
- Ehrlich vor gefaellig: Sag klar, wenn du etwas nicht weisst oder dir unsicher bist. Erfinde nie
  Fakten, Zahlen, Namen oder Quellen. Fuer Aktuelles (Nachrichten, Preise, Termine) nutze die Websuche.
- Gib eine Empfehlung statt einer Liste aller Moeglichkeiten. Begruende kurz, wenn es hilft.
- Widersprich hoeflich, wenn er etwas Falsches annimmt oder sich etwas schadet.

Wie du sprichst (deine Antwort wird VORGELESEN):
- Deutsch, natuerlich und locker, duzen.
- Kurz: meistens 1 bis 3 Saetze. Nur laenger, wenn er ausdruecklich Details will.
- Kein Markdown, keine Listen-Zeichen, keine Emojis, keine URLs vorlesen.
- Zahlen und Uhrzeiten so schreiben, wie man sie sagt."""
import identitaet
PERSONA = identitaet.anpassen_persona(PERSONA)   # Assistenten-/Nutzername aus der Installation



# ------------------------------------------------------------------ Gedaechtnis (Obsidian-Vault)
# Die Notiz Nikola.md ist die echte Quelle: was er in Obsidian aendert oder loescht, gilt sofort.
FAKT_ZEILE = re.compile(r"^- (?P<text>.+?)(?: \(seit (?P<datum>[\d.]+)\))?\s*$")
KOPF = """---
tags: [klaus, gedaechtnis]
---
# Nikola

Was Klaus über dich weiß. Bearbeite oder lösche hier frei – Klaus liest diese Liste bei jedem Gespräch.
Neue Fakten: eine Zeile mit „- “ unter **Fakten**.

## Fakten
"""


def _eintrag(text: str, datum: str) -> dict:
    return {"id": zlib.crc32(text.lower().encode()), "text": text, "datum": datum}


def _uebernehme_alte_liste() -> None:
    """Einmalig: frueheres data/gedaechtnis.json in den Vault uebernehmen."""
    if FAKTEN_PATH.exists() or not GEDAECHTNIS_PATH.exists():
        return
    try:
        alt = json.loads(GEDAECHTNIS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        alt = []
    _speichern([_eintrag(e["text"], e.get("datum", "")) for e in alt])
    GEDAECHTNIS_PATH.rename(GEDAECHTNIS_PATH.with_suffix(".json.bak"))


def lade_gedaechtnis() -> list[dict]:
    _uebernehme_alte_liste()
    try:
        zeilen = FAKTEN_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    eintraege, in_fakten = [], False
    for zeile in zeilen:
        if zeile.startswith("## "):
            in_fakten = zeile.strip().lower() == "## fakten"
        elif in_fakten and (m := FAKT_ZEILE.match(zeile.strip())):
            eintraege.append(_eintrag(m.group("text").strip(), m.group("datum") or ""))
    return eintraege


def _speichern(eintraege: list[dict]) -> None:
    FAKTEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    zeilen = [f"- {e['text']}" + (f" (seit {e['datum']})" if e.get("datum") else "") for e in eintraege]
    FAKTEN_PATH.write_text(KOPF + "\n".join(zeilen) + "\n", encoding="utf-8")


def merke(text: str) -> None:
    text = text.strip(" .,!")
    if not text:
        return
    with _sperre:
        eintraege = [e for e in lade_gedaechtnis() if e["text"].lower() != text.lower()]
        eintraege.append(_eintrag(text, f"{dt.date.today():%d.%m.%Y}"))
        _speichern(eintraege)


# ------------------------------------------------------------------ Vault-Notizen (Gespraeche, Projekte, Briefings)
def _anhaengen(pfad: Path, kopf: str, text: str) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with _sperre:
        neu = not pfad.exists()
        with open(pfad, "a", encoding="utf-8") as f:
            if neu:
                f.write(kopf)
            f.write(text)


def protokolliere(rolle: str, text: str) -> None:
    """Tagesprotokoll der Gespraeche: Gespraeche/2026-10-05.md"""
    if not PROTOKOLL or rolle not in ("du", "klaus") or not text.strip():
        return
    heute = dt.date.today()
    _anhaengen(VAULT / "Gespraeche" / f"{heute:%Y-%m-%d}.md",
               f"---\ntags: [klaus, gespraech]\n---\n# Gespräche {heute:%d.%m.%Y}\n\nmit [[Nikola]]\n\n",
               f"**{dt.datetime.now():%H:%M} {'Du' if rolle == 'du' else 'Klaus'}:** {text.strip()}\n\n")


def notiere_projekt(name: str, auftrag: str, ordner: Path) -> None:
    dateiname = re.sub(r'[\\/:*?"<>|]', "", name)[:60] or "Projekt"
    _anhaengen(VAULT / "Projekte" / f"{dateiname}.md",
               f"---\ntags: [klaus, projekt]\n---\n# {name}\n\nfür [[Nikola]] · gebaut von Claude\n\n",
               f"## Auftrag vom {dt.datetime.now():%d.%m.%Y %H:%M}\n\nOrdner: `{ordner}`\n\n{auftrag.strip()}\n\n")


def notiere_briefing(text: str) -> None:
    heute = dt.date.today()
    _anhaengen(VAULT / "Briefings" / f"{heute:%Y-%m-%d}.md",
               f"---\ntags: [klaus, briefing]\n---\n# Briefings {heute:%d.%m.%Y}\n\n",
               f"## {dt.datetime.now():%H:%M} · Seit du weg warst\n\n{text.strip()}\n\n")


def vergiss(stichwort: str) -> int:
    """Loescht alle Eintraege, die das Stichwort enthalten. Gibt die Anzahl zurueck."""
    woerter = [w for w in re.findall(r"\w{3,}", stichwort.lower()) if w not in {"dass", "das", "ich", "mich", "mein", "meine"}]
    if not woerter:
        return 0
    with _sperre:
        eintraege = lade_gedaechtnis()
        bleiben = [e for e in eintraege if not all(w in e["text"].lower() for w in woerter)]
        _speichern(bleiben)
    return len(eintraege) - len(bleiben)


def vergiss_id(eintrag_id: int) -> None:
    with _sperre:
        _speichern([e for e in lade_gedaechtnis() if e["id"] != eintrag_id])


def gedaechtnis_text() -> str:
    eintraege = lade_gedaechtnis()[-60:]
    if not eintraege:
        return ""
    return "\n\nWas du dir ueber ihn gemerkt hast (nutze es, wenn es passt):\n" + "\n".join(
        f"- {e['text']} (seit {e['datum']})" for e in eintraege
    )


# ------------------------------------------------------------------ Claude-Gehirn
VAULT_HINWEIS = (f"Deine Notizen liegen als Obsidian-Vault in '{VAULT}' (Gespraeche/<Datum>.md, Projekte/, Briefings/, "
                 "Nikola.md). Bezieht er sich auf frueher Besprochenes, lies dort nach, bevor du antwortest.")
# Kurze Kommandos/Smalltalk bleiben lokal (schnell); Fragen, die Denken oder Aktuelles brauchen, gehen an Claude
# Claude nur, wenn Nikola es ausdruecklich sagt ("frag Claude", "lass Claude ...")
NACH_CLAUDE = re.compile(r"\bclaude\b", re.I)
# Fragen, die Wissen von heute brauchen -> Recherche (Tavily + Gemini) statt nur Ollama
NACH_RECHERCHE = re.compile(
    r"\b(denk\w*|(ü|ue)berleg\w*|recherch\w*|erkl(ä|ae)r\w*|warum|wieso|weshalb|wie funktioniert|"
    r"vergleich\w*|empfiehl\w*|empfehl\w*|plan\w*|strategie|aktuell\w*|heute|neuigkeit\w*|news|nachrichten|"
    r"code|programmier\w*|fehler|bug|preis\w*|kosten)\b", re.I)


def soll_claude(frage: str) -> bool:
    if MODUS == "lokal" or not shutil.which("claude"):
        return False
    return bool(NACH_CLAUDE.search(frage))


def soll_recherchieren(frage: str) -> bool:
    return MODUS != "lokal" and (bool(NACH_RECHERCHE.search(frage)) or len(frage.split()) > 12)


def _sprechbar(text: str) -> str:
    """Markdown-Reste entfernen, damit nichts Komisches vorgelesen wird."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [Text](Link) -> Text
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>|]", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


class ClaudeGehirn:
    def __init__(self) -> None:
        self.sitzung: str | None = None
        self.zuletzt = 0.0

    def frage(self, text: str, claude: bool = False) -> str:
        """Standard: Recherche ueber Tavily + Gemini. claude=True nur, wenn Nikola Claude ausdruecklich will
        (Limit leer / kein Netz -> trotzdem Recherche)."""
        if claude:
            try:
                antwort = self._claude(text)
                if antwort.strip():
                    return antwort
            except Exception as e:
                print(f"[Gehirn] Claude nicht verfuegbar ({str(e)[:120]}) - recherchiere ohne Claude.")
        import recherche
        jetzt = dt.datetime.now().strftime("%A, %d.%m.%Y, %H:%M Uhr")
        return _sprechbar(recherche.recherchiere(text, f"{PERSONA}\n\nJetzt ist {jetzt}.{gedaechtnis_text()}"))

    def _claude(self, text: str) -> str:
        if not shutil.which("claude"):
            raise RuntimeError("claude nicht installiert")
        if time.time() - self.zuletzt > SITZUNG_VERGESSEN_SEK:
            self.sitzung = None
        ARBEITSORDNER.mkdir(parents=True, exist_ok=True)
        jetzt = dt.datetime.now().strftime("%A, %d.%m.%Y, %H:%M Uhr")
        befehl = [shutil.which("claude"), "-p", text, "--output-format", "json", "--model", MODELL,
                  "--append-system-prompt", f"{PERSONA}\n\nJetzt ist {jetzt}.{gedaechtnis_text()}\n\n{VAULT_HINWEIS}",
                  "--add-dir", str(VAULT)]
        if self.sitzung:
            befehl += ["--resume", self.sitzung]
        befehl += ["--allowedTools", "WebSearch", "WebFetch"]  # variadisch -> ans Ende
        ergebnis = subprocess.run(
            befehl, cwd=ARBEITSORDNER, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            daten = json.loads(ergebnis.stdout)
        except json.JSONDecodeError:
            raise RuntimeError((ergebnis.stdout or ergebnis.stderr or "keine Antwort")[:200])
        if daten.get("is_error"):
            raise RuntimeError(daten.get("result", "Claude-Fehler"))
        self.sitzung = daten.get("session_id") or self.sitzung
        self.zuletzt = time.time()
        return _sprechbar(daten.get("result", ""))
