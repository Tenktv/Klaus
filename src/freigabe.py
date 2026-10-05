"""
Klaus - Freigabe-Gate: alles mit Wirkung nach aussen (Hochladen, Drucken, Loeschen, spaeter Senden/Anrufen/Handeln)
laeuft nur mit einem Einmal-Token, das ausschliesslich hier entsteht - nach deinem Klick auf "Freigeben" im Panel
oder wenn DU "Freigeben" sagst (deine eigene Sprache: lokales Whisper bzw. Gemini-Mitschrift deines Mikrofons,
nie eine Entscheidung der KI).

    token = freigabe.anfragen("drucken", "6 Briefe drucken", an="Standarddrucker", anzahl=6)   # blockiert, max. 90 s
    hochladen.drucken(token)            # prueft und verbraucht das Token, sonst PermissionError

Die Ausfuehr-Funktionen rufen selbst freigabe.pruefe(token, art) auf - ohne gueltiges Token passiert nichts.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

WARTEZEIT = 90          # so lange wartet eine Anfrage, dann gilt sie als abgebrochen
TOKEN_GUELTIG = 120     # ein erteiltes Token muss innerhalb dieser Zeit benutzt werden

JA = re.compile(r"\b(freigeben|freigabe erteilt|gib (es |das )?frei|ich gebe (es |das )?frei|genehmigt|best(ä|ae)tigt)\b", re.I)
NEIN = re.compile(r"\b(abbrechen|abbruch|nicht freigeben|stopp?|lass es|nein,? nicht)\b", re.I)


@dataclass
class _Anfrage:
    id: str
    art: str
    was: str
    an: str
    anzahl: int
    erstellt: float = field(default_factory=time.time)
    ereignis: threading.Event = field(default_factory=threading.Event)
    ok: bool = False
    wie: str = ""


_sperre = threading.Lock()
_offen: dict[str, _Anfrage] = {}
_tokens: dict[str, tuple[str, float]] = {}   # token -> (art, erteilt um)
_protokoll: list[str] = []
# Wird von assistent.py gesetzt: zeigt/schliesst das Freigabe-Fenster im Panel und setzt den Core-Zustand
melden: Callable[[str, _Anfrage | None], None] = lambda ereignis, anfrage: None


def _log(text: str) -> None:
    _protokoll.append(f"{time.strftime('%H:%M:%S')} {text}")
    del _protokoll[:-200]
    print(f"[Freigabe] {text}")


def offen() -> bool:
    with _sperre:
        return bool(_offen)


def anfragen(art: str, was: str, an: str = "", anzahl: int = 1, wartezeit: float = WARTEZEIT) -> str | None:
    """Fragt dich um Freigabe und wartet. -> Einmal-Token oder None (abgelehnt / Zeit abgelaufen).
    Aus einem Hintergrund-Thread aufrufen (blockiert)."""
    a = _Anfrage(id=secrets.token_hex(4), art=art, was=was, an=an, anzahl=anzahl)
    with _sperre:
        _offen[a.id] = a
    _log(f"angefragt {a.id}: {art} · {was}")
    melden("auf", a)
    a.ereignis.wait(wartezeit)
    with _sperre:
        _offen.pop(a.id, None)
    melden("zu", a)
    if not a.ok:
        _log(f"nicht freigegeben {a.id}: {a.wie or 'Zeit abgelaufen'}")
        return None
    token = secrets.token_urlsafe(24)
    with _sperre:
        _tokens[token] = (art, time.time())
    _log(f"freigegeben {a.id} ({a.wie})")
    return token


def entscheide(anfrage_id: str | None, ok: bool, wie: str) -> bool:
    """Klick im Panel (mit id) oder deine Sprache (id None = neueste offene Anfrage). -> ob es eine offene Anfrage gab."""
    with _sperre:
        if anfrage_id:
            a = _offen.get(anfrage_id)
        else:
            a = max(_offen.values(), key=lambda x: x.erstellt) if _offen else None
    if not a or a.ereignis.is_set():
        return False
    a.ok, a.wie = ok, wie
    a.ereignis.set()
    return True


def sprache(text: str, quelle: str) -> bool:
    """Deine gesprochenen Worte (nie Text der KI!) - entscheidet die offene Anfrage, wenn "Freigeben"/"Abbrechen" drin ist."""
    if not text or not offen():
        return False
    if NEIN.search(text):
        return entscheide(None, False, f"Sprache ({quelle}): {text.strip()[:40]}")
    if JA.search(text):
        return entscheide(None, True, f"Sprache ({quelle}): {text.strip()[:40]}")
    return False


def pruefe(token: str | None, art: str) -> None:
    """Von den Ausfuehr-Funktionen aufzurufen: Token muss zur Art passen, frisch und unbenutzt sein. Verbraucht es."""
    with _sperre:
        eintrag = _tokens.pop(token or "", None)
    if not eintrag:
        raise PermissionError(f"{art}: keine Freigabe")
    if eintrag[0] != art:
        raise PermissionError(f"{art}: Freigabe gilt nur für {eintrag[0]}")
    if time.time() - eintrag[1] > TOKEN_GUELTIG:
        raise PermissionError(f"{art}: Freigabe abgelaufen")
    _log(f"ausgefuehrt: {art}")


def im_hintergrund(art: str, was: str, ausfuehren: Callable[[str], str], fertig: Callable[[str], None],
                   an: str = "", anzahl: int = 1) -> None:
    """Fuer Werkzeuge, die sofort antworten muessen (Gemini Live): fragen, warten, dann ausfuehren(token) -> fertig(text)."""
    def los() -> None:
        token = anfragen(art, was, an, anzahl)
        if not token:
            fertig(f"Nicht freigegeben, ich habe nichts gemacht ({was}).")
            return
        try:
            fertig(ausfuehren(token))
        except Exception as e:
            fertig(f"Das hat nicht geklappt: {str(e)[:120]}")

    threading.Thread(target=los, daemon=True).start()
