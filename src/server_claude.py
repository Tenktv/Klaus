"""
Klaus - Claude Code auf dem SERVER (Cloud), damit Fragen an Claude und Bauauftraege auch gehen, wenn der PC aus ist.

    server_claude.status()                 ist `claude` installiert und angemeldet?
    server_claude.frage(text)              wie frage_claude am PC: Antwort mit Websuche
    server_claude.bauen(auftrag, name, fertig)   baut im Hintergrund in ~/projekte/<name>, meldet sich per fertig(text, zip)

Anmeldung (einmal): `claude setup-token` am PC ausfuehren und den Token per Telegram `/claude_token <token>` schicken
(Nachricht wird sofort geloescht, geht nie an die KI) - oder ANTHROPIC_API_KEY in der .env des Servers.
Server-Claude arbeitet nur in ~/claude-arbeit und ~/projekte, ohne Shell; Klaus' Schluessel gibt es ihm nicht mit.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
HEIM = Path.home()
ARBEIT = HEIM / "claude-arbeit"
PROJEKTE = HEIM / "projekte"
MODELL = os.getenv("CLAUDE_SERVER_MODELL", "sonnet")
FRAGE_FRIST_S = 140   # unter der Werkzeug-Frist von Telegram (150 s)
BAU_FRIST_S = 45 * 60
PERSONA = ("Du hilfst Klaus, dem persoenlichen Assistenten von Nikola. Antworte auf Deutsch, knapp und als Fliesstext "
           "ohne Markdown - die Antwort wird per Telegram weitergegeben.")
_bau_sperre = threading.Lock()


def _programm() -> str | None:
    for kandidat in (shutil.which("claude"), str(HEIM / ".local/bin/claude"), str(HEIM / ".npm-global/bin/claude"),
                     "/usr/local/bin/claude", "/usr/bin/claude"):
        if kandidat and Path(kandidat).exists():
            return kandidat
    return None


def angemeldet() -> bool:
    return bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "").strip() or os.getenv("ANTHROPIC_API_KEY", "").strip()
                or (HEIM / ".claude" / ".credentials.json").exists())


def status() -> str:
    if not _programm():
        return ("Claude Code ist auf dem Server nicht installiert. Einmal per SSH als Benutzer klaus: "
                "curl -fsSL https://claude.ai/install.sh | bash")
    if not angemeldet():
        return ("Claude Code ist installiert, aber nicht angemeldet. Am PC `claude setup-token` ausführen und mir den Token "
                "mit /claude_token <token> schicken (ich lösche die Nachricht sofort).")
    return "Claude Code auf dem Server ist bereit."


def _umgebung() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ALPACA_", "TELEGRAM_", "KLAUS_", "APPLE_", "GEMINI_",
                                                                    "FISH_", "KLESRO_", "TAVILY_"))}
    env["HOME"] = str(HEIM)
    return env


def _laufen(befehl: list[str], ordner: Path, frist: int) -> dict:
    ordner.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=frist, env=_umgebung())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude hat länger als {frist // 60} Minuten gebraucht und wurde abgebrochen.")
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError((r.stderr or r.stdout or "keine Antwort").strip()[-300:])
    if d.get("is_error"):
        raise RuntimeError(str(d.get("result") or "Claude-Fehler")[:300])
    return d


def _bereit() -> str:
    programm = _programm()
    if not programm or not angemeldet():
        raise RuntimeError(status())
    return programm


def frage(text: str) -> str:
    """Einzelne Frage an Claude (mit Websuche). Fehler kommen als verstaendlicher Text zurueck."""
    try:
        programm = _bereit()
        d = _laufen([programm, "-p", text, "--output-format", "json", "--model", MODELL,
                     "--append-system-prompt", PERSONA, "--allowedTools", "WebSearch", "WebFetch"], ARBEIT, FRAGE_FRIST_S)
    except RuntimeError as e:
        return f"Claude (Server) geht gerade nicht: {e}"
    return re.sub(r"[*_#`]", "", str(d.get("result", ""))).strip() or "Claude hat nichts geantwortet."


def _ordnername(name: str) -> str:
    sauber = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss"))
    return sauber.strip("-")[:40] or "projekt"


def _zip(ordner: Path) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for datei in ordner.rglob("*"):
            if datei.is_file() and ".git" not in datei.parts and "node_modules" not in datei.parts:
                z.write(datei, datei.relative_to(ordner))
    return puffer.getvalue()


def bauen(auftrag: str, name: str, fertig) -> str:
    """Startet den Bau im Hintergrund. fertig(text, zip_bytes|None, dateiname) wird am Ende aufgerufen."""
    try:
        programm = _bereit()
    except RuntimeError as e:
        return f"Claude (Server) geht gerade nicht: {e}"
    if not _bau_sperre.acquire(blocking=False):
        return "Claude baut auf dem Server gerade schon etwas – ich melde mich, wenn das fertig ist."
    ordner = PROJEKTE / _ordnername(name)

    def los() -> None:
        try:
            d = _laufen([programm, "-p", f"Baue dieses Projekt in diesem Ordner: {auftrag}\n\nAm Ende: kurze Zusammenfassung auf "
                         "Deutsch, was gebaut wurde und was noch Platzhalter ist.", "--output-format", "json",
                         "--model", MODELL, "--permission-mode", "acceptEdits",
                         "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"], ordner, BAU_FRIST_S)
            zusammenfassung = re.sub(r"[*_#`]", "", str(d.get("result", ""))).strip()[:1500]
            daten = _zip(ordner)
            if len(daten) > 45 * 1024 * 1024:
                fertig(f"✅ „{name}“ ist fertig (Server: {ordner}), aber zu groß zum Schicken.\n{zusammenfassung}", None, "")
            else:
                fertig(f"✅ Claude ist fertig mit „{name}“.\n{zusammenfassung}", daten, f"{_ordnername(name)}.zip")
        except Exception as e:
            fertig(f"Beim Bauen von „{name}“ auf dem Server gab es einen Fehler: {str(e)[:300]}", None, "")
        finally:
            _bau_sperre.release()

    threading.Thread(target=los, daemon=True, name="klaus-claude-bau").start()
    return f"Dein PC ist aus – Claude baut „{name}“ jetzt in der Cloud (Server). Ich schicke dir das Ergebnis als ZIP."


def token_setzen(eingabe: str, speichern) -> str:
    """/claude_token <token> - Token aus `claude setup-token` (beginnt mit sk-ant-oat). Nachricht wird vorher geloescht."""
    teile = eingabe.split()
    if len(teile) != 2:
        return "So: /claude_token <token> – den Token bekommst du am PC mit `claude setup-token`. Ich lösche die Nachricht sofort."
    token = teile[1].strip()
    if not re.fullmatch(r"sk-ant-oat[0-9A-Za-z_\-]{20,300}", token):
        return "Das sieht nicht nach einem Token aus `claude setup-token` aus (beginnt mit sk-ant-oat) – nichts gespeichert."
    speichern("CLAUDE_CODE_OAUTH_TOKEN", token)
    return "🔑 Claude-Token gespeichert, deine Nachricht ist gelöscht. " + status()
