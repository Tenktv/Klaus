"""
Klaus - Sprachmodus
Mit Klaus per Mikrofon sprechen, gemeinsam einen Plan entwickeln und ihn dann
an Claude Code uebergeben, das ihn in einem eigenen Projektordner umsetzt.

Ablauf:
    Einfach sprechen - Klaus erkennt Anfang und Ende (Pause) selbst und antwortet per Stimme.
    Mit --ptt stattdessen: Enter druecken -> sprechen -> Enter druecken.
    Sprachbefehle:
        "an Claude geben" / "bau das" / "umsetzen"  -> Plan an Claude Code uebergeben
        "neu anfangen"                                -> Gespraech zuruecksetzen
        "beenden" / "tschuess"                        -> Programm beenden

Nutzung:
    .venv/Scripts/python src/voice.py              # Mikrofon + Stimme
    .venv/Scripts/python src/voice.py --ptt        # mit Enter-Taste aufnehmen (und tippen erlaubt)
    .venv/Scripts/python src/voice.py --text       # tippen statt sprechen (zum Testen)
    .venv/Scripts/python src/voice.py --dry-run    # Claude nicht wirklich starten

.env (optional):
    WHISPER_MODEL   (Standard: small)   - tiny/base/small/medium/large-v3
    KLAUS_MIC       (Standard: System)  - Teil des Mikrofon-Namens, z.B. "USB"
    CLAUDE_PERMISSION_MODE (Standard: acceptEdits)
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import os
import queue
import re
import shutil
import site
import subprocess
import sys
from pathlib import Path


def _cuda_dlls() -> None:
    """Macht die per pip installierten CUDA-DLLs (cuBLAS/cuDNN) fuer Whisper auffindbar."""
    for sp in site.getsitepackages():
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


_cuda_dlls()

from dotenv import load_dotenv

import llm
import stimme

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROJEKTE_DIR = BASE_DIR / "data" / "projekte"
LEAD_DATEIEN = [BASE_DIR / "data" / "leads.csv", BASE_DIR / "data" / "leads_sample.csv"]

ABSENDER_NAME = os.getenv("KLESRO_ABSENDER_NAME", "Nikola Georgiev")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
KLAUS_MIC = os.getenv("KLAUS_MIC", "")
PERMISSION_MODE = os.getenv("CLAUDE_PERMISSION_MODE", "acceptEdits")
ERSATZ_STIMME = "data/stimmen/de_DE-thorsten-high.onnx"
KLAUS_STIMME = os.getenv("KLAUS_STIMME", "").strip() or ERSATZ_STIMME
SCHWELLE = float(os.getenv("KLAUS_SCHWELLE", "0"))  # 0 = automatisch kalibrieren
PAUSE_SEK = float(os.getenv("KLAUS_PAUSE", "1.2"))  # so lange Stille = Satz zu Ende
SAMPLE_RATE = 16000
BLOCK_SEK = 0.03
# Hilft Whisper bei Fachwoertern und Namen (Firmennamen aus der Leadliste kommen dazu)
WORTSCHATZ = "Klaus, Claude, Website, Webseite, Landingpage, Klesro Web, Göppingen, "
FLOSKELN = re.compile(r"untertitel|amara\.org|f(ü|ue)rs zuschauen|zdf|swr|copyright|abonnier", re.I)

SYSTEM = f"""Du bist Klaus, der Sprach-Assistent von {ABSENDER_NAME} (Klesro Web, Webdesign im Raum Goeppingen).
Du planst gemeinsam mit {ABSENDER_NAME} Projekte, vor allem Websites fuer lokale Firmen.
Deine Antworten werden VORGELESEN: antworte kurz (2-4 Saetze), ohne Markdown, ohne Listen-Zeichen.
Stelle pro Antwort hoechstens eine gezielte Rueckfrage, um den Plan zu schaerfen
(z.B. Seiten, Stil, Farben, Inhalte, Kontaktmoeglichkeiten, Technik).
Du baust nichts selbst. Wenn der Plan rund ist, schlage vor, ihn an Claude zu uebergeben
(der Nutzer sagt dann "an Claude geben")."""
import identitaet
SYSTEM = identitaet.anpassen(SYSTEM)


PROMPT_BAUEN = """Fasse das bisherige Gespraech zu einem vollstaendigen Arbeitsauftrag fuer Claude Code
(einen KI-Programmierer) zusammen. Claude arbeitet in einem leeren Projektordner.
Schreibe auf Deutsch, als klare Anweisung, mit:
- Ziel und Firma (inkl. aller bekannten Firmendaten)
- Seiten/Abschnitte und Inhalte
- Design (Stil, Farben, Schrift, Stimmung)
- Technik (falls nicht besprochen: statisches HTML/CSS/JS, responsiv, ohne Build-Schritt)
- Was am Ende im Ordner liegen soll
Erfinde keine Fakten ueber die Firma; markiere fehlende Inhalte als Platzhalter.
Gib NUR den Auftrag aus, keine Einleitung."""

BEFEHL_UEBERGEBEN = re.compile(r"\b(an claude|claude geben|bau (das|es)|umsetzen|leg los)\b", re.I)
BEFEHL_RESET = re.compile(r"\b(neu anfangen|von vorne)\b", re.I)
BEFEHL_ENDE = re.compile(r"\b(beenden|tsch(ü|ue)ss|auf wiedersehen)\b", re.I)
JA = re.compile(r"\b(ja|jawohl|genau|mach|los|ok|okay|passt)\b", re.I)


# ---------------------------------------------------------------- Stimme raus
def sprich(text: str, stumm: bool, on_pegel=None, abbruch=None) -> None:
    print(f"\nKlaus: {text}\n")
    import betrieb
    if stumm or betrieb.ruhe() or (abbruch and abbruch()):
        return
    text = re.sub(r"[*#_`>]", "", text)
    # Gewaehlte Stimme, sonst lokale Piper-Ersatzstimme. Keine ununterbrechbare Windows-TTS.
    import stimmwahl
    gewaehlt = stimmwahl.lokale_kennung()   # in Telegram/Panel gewaehlte Stimme (Gemini-Stimmen gibt es lokal nicht)
    for kennung in dict.fromkeys([k for k in (gewaehlt, KLAUS_STIMME, ERSATZ_STIMME) if k]):
        try:
            stimme.sprich(kennung, text, on_pegel=on_pegel, abbruch=abbruch)
            return
        except InterruptedError:
            return
        except Exception as e:
            print(f"  (Stimme {stimme.name(kennung)} fehlgeschlagen: {str(e)[:80]})")
    print('  (Keine unterbrechbare Stimme verfuegbar; Antwort bleibt als Text.)')


# ----------------------------------------------------------------- Stimme rein
def _whisper_laden(WhisperModel, modell: str, **optionen):
    """Laedt das Whisper-Modell. Ist der Download beim ersten Start abgebrochen (model.bin fehlt im Cache),
    wird der kaputte Cache-Ordner geloescht und einmal neu geladen - sonst startet Klaus nie wieder."""
    try:
        return WhisperModel(modell, **optionen)
    except RuntimeError as e:
        m = re.search(r"in model '([^']+)'", str(e))
        if "model.bin" not in str(e) or not m:
            raise
        ordner = Path(m.group(1))
        while ordner.parent != ordner and not ordner.name.startswith("models--"):
            ordner = ordner.parent
        if not ordner.name.startswith("models--"):
            raise
        print(f"  Download der Spracherkennung war unvollstaendig - lade neu ({ordner.name})")
        shutil.rmtree(ordner, ignore_errors=True)
        return WhisperModel(modell, **optionen)


class Ohr:
    def __init__(self, freihand: bool = True) -> None:
        import numpy as np
        from faster_whisper import WhisperModel

        print(f"Lade Spracherkennung '{WHISPER_MODEL}' (beim ersten Mal wird sie heruntergeladen) ...")
        try:
            # int8_float16: etwa halber Grafikspeicher gegenueber float16, kaum schlechter
            self.model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="int8_float16")
            segmente, _ = self.model.transcribe(np.zeros(SAMPLE_RATE, dtype="float32"))
            list(segmente)
            print("  -> laeuft auf der Grafikkarte")
        except Exception as e:
            # medium/large sind auf der CPU zu langsam fuers Gespraech -> small
            cpu_modell = WHISPER_MODEL if WHISPER_MODEL in ("tiny", "base", "small") else "small"
            print(f"  (Grafikkarte nicht nutzbar: {str(e)[:80]})")
            self.model = _whisper_laden(WhisperModel, cpu_modell, device="cpu", compute_type="int8")
            print(f"  -> laeuft auf der CPU ({cpu_modell})")
        self.geraet = self._finde_mikro()
        self.freihand = freihand
        self.firmen = [r["name"] for r in lade_leads()][:50]
        self.schwelle = SCHWELLE or (self._kalibriere() if freihand else 0)

    @staticmethod
    def _finde_mikro():
        if not KLAUS_MIC:
            return None
        import sounddevice as sd

        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and KLAUS_MIC.lower() in d["name"].lower():
                print(f"  Mikrofon: {d['name']}")
                return i
        print(f"  Mikrofon '{KLAUS_MIC}' nicht gefunden - nutze Standard.")
        return None

    def _kalibriere(self) -> float:
        """Misst 1,5 s Raumrauschen und legt die Sprech-Schwelle darueber."""
        import numpy as np
        import sounddevice as sd

        print("  Kalibriere Mikrofon - bitte kurz still sein ...")
        a = sd.rec(int(SAMPLE_RATE * 1.5), samplerate=SAMPLE_RATE, channels=1,
                   dtype="float32", device=self.geraet)
        sd.wait()
        blocke = a[: len(a) // 480 * 480, 0].reshape(-1, 480)
        # Ruhigstes Fuenftel zaehlt (ein Geraeusch beim Start verdirbt sonst die Schwelle), dazu eine Obergrenze
        rauschen = float(np.percentile(np.sqrt((blocke ** 2).mean(axis=1)), 20))
        schwelle = self._begrenzt(rauschen * 3.0)
        print(f"  Rauschen {rauschen:.5f} -> Schwelle {schwelle:.5f} (fest setzen: KLAUS_SCHWELLE in .env)")
        return schwelle

    @staticmethod
    def _begrenzt(schwelle: float) -> float:
        # Obergrenze: das IC-Mikro ist leise - eine zu hohe Schwelle heisst "Klaus hoert nichts mehr"
        return float(min(max(schwelle, 0.0002), 0.0015))

    def _nachmessen(self, rms: float) -> None:
        """Im Ruhezustand laufend nachkalibrieren (alle ~10 s), damit eine verkorkste Startmessung heilt."""
        if SCHWELLE:
            return
        if not hasattr(self, "_ruhewerte"):
            self._ruhewerte = []
        self._ruhewerte.append(rms)
        if len(self._ruhewerte) >= int(10 / BLOCK_SEK):
            import numpy as np

            neu = self._begrenzt(float(np.percentile(self._ruhewerte, 20)) * 3.0)
            if abs(neu - self.schwelle) / self.schwelle > 0.3:
                print(f"  Schwelle nachgemessen: {self.schwelle:.5f} -> {neu:.5f}")
            self.schwelle = neu
            self._ruhewerte = []

    def hoere(self) -> str:
        return self._hoere_frei() if self.freihand else self._hoere_taste()

    def _hoere_frei(self, timeout=None, abbruch=None, on_pegel=None, on_start=None) -> str:
        """Wartet, bis gesprochen wird, und nimmt bis zur naechsten Pause auf.

        timeout:  Sekunden, nach denen ohne Sprache "" zurueckkommt
        abbruch:  Funktion -> True bricht das Warten ab
        on_pegel: bekommt laufend die Lautstaerke 0..1 (fuer Animationen)
        on_start: wird aufgerufen, sobald Sprache erkannt wurde
        """
        import numpy as np
        import sounddevice as sd

        q: queue.Queue = queue.Queue()
        block = int(SAMPLE_RATE * BLOCK_SEK)
        vorlauf = collections.deque(maxlen=int(0.4 / BLOCK_SEK))  # Satzanfang nicht abschneiden
        teile, laut, stille, spricht, gewartet = [], 0, 0, False, 0
        if on_pegel is None:
            print("  (hoere zu - einfach sprechen, Strg+C = beenden)")
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.geraet,
                            blocksize=block, callback=lambda d, *_: q.put(d[:, 0].copy())):
            while True:
                b = q.get()
                rms = float(np.sqrt((b ** 2).mean()))
                ueber = rms > self.schwelle
                if on_pegel:
                    on_pegel(min(1.0, rms / (self.schwelle * 12)))
                if not spricht:
                    gewartet += 1
                    if (timeout and gewartet * BLOCK_SEK > timeout) or (abbruch and abbruch()):
                        return ""
                    self._nachmessen(rms)
                    vorlauf.append(b)
                    laut = laut + 1 if ueber else 0
                    if laut >= 4:  # ~120 ms am Stueck laut -> Sprache
                        spricht, teile = True, list(vorlauf)
                        if on_start:
                            on_start()
                        else:
                            print("  ... nehme auf")
                else:
                    teile.append(b)
                    stille = 0 if ueber else stille + 1
                    if stille * BLOCK_SEK >= PAUSE_SEK or len(teile) * BLOCK_SEK > 60:
                        break
        return self._transkribiere(np.concatenate(teile))

    def _hoere_taste(self) -> str:
        import numpy as np
        import sounddevice as sd

        getippt = input("[Enter] = Aufnahme starten (oder einfach tippen) ").strip()
        if getippt:
            return getippt
        teile = []
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.geraet,
            callback=lambda data, *_: teile.append(data.copy()),
        )
        with stream:
            input("  ... ich hoere zu. [Enter] = fertig ")
        if not teile:
            return ""
        return self._transkribiere(np.concatenate(teile)[:, 0])

    def _transkribiere(self, audio) -> str:
        import numpy as np

        spitze = float(np.abs(audio).max())
        if spitze < 0.0005:
            print("  ! Kein Ton aufgenommen - falsches Mikrofon? KLAUS_MIC in .env pruefen.")
            return ""
        audio = audio * (0.9 / spitze)  # leise Mikros auf volle Lautstaerke anheben
        hinweis = WORTSCHATZ + ", ".join(self.firmen)
        segmente, _ = self.model.transcribe(
            audio, language="de", vad_filter=True, initial_prompt=hinweis, condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segmente).strip()
        if text and self._halluziniert(text, hinweis):
            print(f"  (verworfen, kein echtes Gesprochenes: {text!r})")
            return ""
        print(f"Du: {text}" if text else "  (nichts verstanden - bitte nochmal)")
        return text

    @staticmethod
    def _halluziniert(text: str, hinweis: str) -> bool:
        """Whisper gibt bei Rauschen gern die Wortliste oder Untertitel-Floskeln aus."""
        if FLOSKELN.search(text):
            return True
        # Ab 3 Woertern, die alle nur aus der Wortliste stammen -> nachgeplappert ("Klaus" allein ist echt)
        woerter = set(re.findall(r"\w+", text.lower()))
        liste = set(re.findall(r"\w+", hinweis.lower()))
        return len(woerter) >= 3 and len(woerter & liste) / len(woerter) >= 0.75  # auch "Schreienerei" statt "Schreinerei"


def tippe() -> str:
    return input("Du: ").strip()


# --------------------------------------------------------------- Lead-Wissen
def lade_leads() -> list[dict]:
    leads = []
    for pfad in LEAD_DATEIEN:
        if pfad.exists():
            with open(pfad, newline="", encoding="utf-8") as f:
                leads += [r for r in csv.DictReader(f) if r.get("name")]
    return leads


def passende_leads(text: str, leads: list[dict]) -> list[dict]:
    """Findet Leads, deren Name (oder ein markantes Wort daraus) im Gesagten vorkommt."""
    t = text.lower()
    treffer = []
    for r in leads:
        woerter = [w for w in re.findall(r"\w+", r["name"].lower()) if len(w) > 3]
        if r["name"].lower() in t or any(w in t for w in woerter):
            treffer.append(r)
    return treffer


def lead_info(r: dict) -> str:
    return (
        f"[Firmendaten aus Klaus-Leadliste] Name: {r.get('name')}; Adresse: {r.get('adresse')}; "
        f"Telefon: {r.get('telefon') or 'unbekannt'}; Google-Bewertung: {r.get('bewertung')} "
        f"({r.get('anzahl_bewertungen')} Bewertungen); Branche: {r.get('branche_suchbegriff')}; "
        f"Website: keine"
    )


# ------------------------------------------------------------ Claude-Uebergabe
def slugify(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "projekt"


def an_claude(auftrag: str, name: str, dry_run: bool) -> Path:
    ordner = PROJEKTE_DIR / f"{dt.date.today():%Y-%m-%d}-{slugify(name)}"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "AUFTRAG.md").write_text(auftrag, encoding="utf-8")

    claude = shutil.which("claude")
    if dry_run or not claude:
        if not claude:
            print("  ! 'claude' nicht im PATH gefunden.")
        print(f"  (Probelauf) Auftrag gespeichert in {ordner / 'AUFTRAG.md'}")
        return ordner

    print(f"\n--- Claude Code arbeitet in {ordner} ---\n")
    proc = subprocess.Popen(
        [claude, "-p", "--permission-mode", PERMISSION_MODE],
        cwd=ordner, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
    )
    proc.stdin.write(auftrag)
    proc.stdin.close()
    ausgabe = []
    for zeile in proc.stdout:
        print(zeile, end="")
        ausgabe.append(zeile)
    proc.wait()
    (ordner / "CLAUDE_ANTWORT.md").write_text("".join(ausgabe), encoding="utf-8")
    print(f"\n--- Claude fertig (Exit-Code {proc.returncode}) ---\n")
    return ordner


# ------------------------------------------------------------------ Planen
class Planer:
    """Das Planungsgespraech - genutzt von der Konsole (voice.py) und der Hintergrund-App."""

    def __init__(self) -> None:
        self.leads = lade_leads()
        self.reset()

    def reset(self) -> None:
        import gehirn  # hier statt oben: voice.py laeuft auch allein als Konsolen-Klaus

        self.verlauf = [{"role": "system", "content": SYSTEM + gehirn.gedaechtnis_text()}]
        self.bekannte: set[str] = set()
        self.projektname = "projekt"

    @property
    def hat_inhalt(self) -> bool:
        return any(m["role"] == "user" for m in self.verlauf)

    def antworte(self, gesagt: str) -> str:
        # Firmendaten aus der Leadliste einspeisen, wenn eine bekannte Firma genannt wird
        for r in passende_leads(gesagt, self.leads):
            if r["name"] not in self.bekannte:
                self.bekannte.add(r["name"])
                self.projektname = r["name"]
                self.verlauf.append({"role": "system", "content": lead_info(r)})
                print(f"  (Firmendaten geladen: {r['name']})")
        self.verlauf.append({"role": "user", "content": gesagt})
        antwort = llm.chat(self.verlauf, temperatur=0.5)
        self.verlauf.append({"role": "assistant", "content": antwort})
        return antwort

    def auftrag(self) -> str:
        auftrag = llm.chat(self.verlauf + [{"role": "user", "content": PROMPT_BAUEN}], temperatur=0.2)
        if self.projektname == "projekt":
            self.projektname = llm.frage(
                "Nenne NUR den Namen der Firma oder des Projekts aus diesem Auftrag (max. 4 Woerter):\n"
                + auftrag, temperatur=0
            ).strip(" .\"'\n")[:40] or "projekt"
        return auftrag


def ist_ja(antwort: str) -> bool:
    return bool(JA.search(antwort or "")) and not re.search(r"\bnein\b", antwort or "", re.I)


# ------------------------------------------------------------------ Hauptloop
def main() -> None:
    import instanz
    if not instanz.sperren():
        print('Klaus laeuft bereits (Desktop oder Voice).')
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="tippen statt sprechen")
    ap.add_argument("--ptt", action="store_true", help="mit Enter-Taste aufnehmen statt freihaendig")
    ap.add_argument("--stumm", action="store_true", help="keine Sprachausgabe")
    ap.add_argument("--dry-run", action="store_true", help="Claude nicht starten, nur Auftrag speichern")
    args = ap.parse_args()

    if not llm.ist_verfuegbar():
        sys.exit(f"Ollama oder Modell '{llm.OLLAMA_MODEL}' nicht erreichbar. Ist Ollama gestartet?")

    hoere = tippe if args.text else Ohr(freihand=not args.ptt).hoere
    planer = Planer()

    sprich("Hallo Nikola, hier ist Klaus. Was wollen wir bauen?", args.stumm)

    while True:
        try:
            gesagt = hoere()
        except (KeyboardInterrupt, EOFError):
            break
        if not gesagt:
            continue

        if BEFEHL_ENDE.search(gesagt):
            sprich("Bis spaeter.", args.stumm)
            break

        if BEFEHL_RESET.search(gesagt):
            planer.reset()
            sprich("Alles klar, wir fangen von vorne an.", args.stumm)
            continue

        if BEFEHL_UEBERGEBEN.search(gesagt) and planer.hat_inhalt:
            print("  (Klaus schreibt den Auftrag fuer Claude ...)")
            auftrag = planer.auftrag()
            print('\n========== AUFTRAG FUER CLAUDE ==========\n' + auftrag + '\n=========================================')
            sprich("Ich habe den Auftrag zusammengefasst, er steht auf dem Bildschirm. "
                   "Soll ich ihn an Claude geben?", args.stumm)
            if ist_ja(hoere()):
                sprich("Okay, Claude legt los. Das kann ein paar Minuten dauern.", args.stumm)
                ordner = an_claude(auftrag, planer.projektname, args.dry_run)
                sprich(f"Fertig. Das Ergebnis liegt im Ordner {ordner.name}.", args.stumm)
            else:
                sprich("Gut, dann feilen wir weiter am Plan.", args.stumm)
            continue

        sprich(planer.antworte(gesagt), args.stumm)


if __name__ == "__main__":
    main()
