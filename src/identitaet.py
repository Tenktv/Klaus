"""
Klaus - wie der Assistent heisst und wie er dich nennt (bei der Installation eingegeben, in der .env).

    KLAUS_NAME=Klaus        Name des Assistenten (Weckwort, Persona). Standard: Klaus
    KLAUS_NUTZER=           dein Name - leer = wie im Code (Nikola)

identitaet.anpassen(text)   ersetzt "Klaus"/"Nikola" in Anweisungen an die KI durch die eingestellten Namen
identitaet.weckwort_muster() Regex-Teil fuers Weckwort ("Klaus, ..." / "Hey Luna, ...")
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

STANDARD_NAME = "Klaus"
NAME = os.getenv("KLAUS_NAME", "").strip() or STANDARD_NAME
NUTZER = os.getenv("KLAUS_NUTZER", "").strip()
# Whisper schreibt "Klaus" oft anders - fuer andere Namen reicht der Name selbst (plus ein paar Schreibweisen)
_KLAUS_VARIANTEN = ["klaus", "claus", "klaas", "kraus", "klause"]


def anpassen(text: str) -> str:
    if NAME != STANDARD_NAME:
        text = re.sub(r"\bKlaus\b", NAME, text)
        text = re.sub(r"\bKLAUS\b", NAME.upper(), text)
    if NUTZER:
        text = re.sub(r"\bNikola(?: Georgiev)?\b", NUTZER, text)
    return text


def fremder_nutzer() -> bool:
    """Installiert jemand anderes als Nikola? Dann keine persoenlichen Angaben ueber Nikola in der Persona."""
    return bool(NUTZER) and not NUTZER.lower().startswith("nikola")


def anpassen_persona(persona: str) -> str:
    """Wie anpassen(), dazu bei anderen Nutzern: erster Absatz (Nikolas Firma, Hobbys) wird neutral."""
    if fremder_nutzer():
        kopf, _, rest = persona.partition("\n\n")
        persona = (f"Du bist {NAME}, der persoenliche Sprach-Assistent von {NUTZER}. Ihr kennt euch - stell dich nicht vor "
                   f"und begruesse nicht, ausser {NUTZER} gruesst.\n\n{rest}" if rest else persona)
    return anpassen(persona)


def weckwort_muster() -> str:
    if NAME == STANDARD_NAME:
        varianten = _KLAUS_VARIANTEN
    else:
        n = NAME.lower()
        varianten = list(dict.fromkeys([n, n.replace("c", "k"), n.replace("k", "c"), n.replace("ph", "f"), n.replace("y", "i")]))
    return "(?:" + "|".join(re.escape(v) for v in varianten) + ")"
