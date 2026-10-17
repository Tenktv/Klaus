"""
Klaus - Claude Code auf dem SERVER (Cloud), damit Fragen an Claude und Bauauftraege auch gehen, wenn der PC aus ist.

    server_claude.status()                 ist `claude` installiert und angemeldet?
    server_claude.frage(text)              wie frage_claude am PC: Antwort mit Websuche
    server_claude.bauen(auftrag, name, fertig)   baut im Hintergrund in ~/projekte/<name>, meldet sich per fertig(text, zip)

Anmeldung (einmal): `claude setup-token` am PC ausfuehren und den Token per Telegram `/claude_token <token>` schicken
(Nachricht wird sofort geloescht, geht nie an die KI) - oder ANTHROPIC_API_KEY in der .env des Servers.
Server-Claude arbeitet nur in ~/claude-arbeit und ~/projekte, ohne Shell; Klaus' Schluessel gibt es ihm nicht mit.

Abgeschottet (Standard auf dem Server, sobald /usr/local/bin/klaus-claude existiert - siehe server/claude-einrichten.sh):
Claude laeuft als eigener Linux-Benutzer `claudebau` (sudo nur fuer genau dieses Startskript). Er kann /home/klaus
(Klaus' Code und .env) nicht lesen, arbeitet in /srv/klaus-claude/{arbeit,projekte} und hat seinen Token selbst.
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
WRAPPER = Path(os.getenv("KLAUS_CLAUDE_WRAPPER", "/usr/local/bin/klaus-claude"))
BAU_BENUTZER = os.getenv("KLAUS_CLAUDE_BENUTZER", "claudebau")
ABGESCHOTTET_BASIS = Path(os.getenv("KLAUS_CLAUDE_BASIS", "/srv/klaus-claude"))


def abgeschottet() -> bool:
    return WRAPPER.exists()


def _wrapper(*args: str, eingabe: str | None = None, frist: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["sudo", "-n", "-H", "-u", BAU_BENUTZER, str(WRAPPER), *args], input=eingabe, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=frist)


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
    if abgeschottet():
        try:
            st = _wrapper("--status").stdout
        except Exception as e:
            return f"Claude auf dem Server ist nicht erreichbar ({str(e)[:80]})."
        if "installiert" not in st:
            return "Claude Code ist für den Benutzer claudebau nicht installiert (server/claude-einrichten.sh ausführen)."
        if "angemeldet" not in st:
            return ("Claude Code ist installiert, aber nicht angemeldet. Am PC `claude setup-token` ausführen und mir den Token "
                    "mit /claude_token <token> schicken (ich lösche die Nachricht sofort).")
        return "Claude Code auf dem Server ist bereit (abgeschottet, eigener Benutzer)."
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


def _projekte() -> Path:
    return ABGESCHOTTET_BASIS / "projekte" if abgeschottet() else PROJEKTE


def _laufen(befehl: list[str], ordner: Path, frist: int) -> dict:
    if abgeschottet():   # als claudebau ueber das Startskript; es wechselt selbst in den Ordner
        ziel = ["arbeit"] if ordner == ARBEIT else ["projekt", ordner.name]
        befehl = ["sudo", "-n", "-H", "-u", BAU_BENUTZER, str(WRAPPER), *ziel, *befehl[1:]]
        ordner, umgebung = BASE_DIR, None
    else:
        ordner.mkdir(parents=True, exist_ok=True)
        umgebung = _umgebung()
    try:
        r = subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=frist, env=umgebung)
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
    if abgeschottet():
        meldung = status()
        if "bereit" not in meldung:
            raise RuntimeError(meldung)
        return "claude"   # das echte Programm startet das Startskript als claudebau
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
    ordner = _projekte() / _ordnername(name)

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
    if abgeschottet():   # der Token gehoert claudebau, nicht in Klaus' .env
        r = _wrapper("--token", eingabe=token + "\n")
        if r.returncode != 0:
            return "Der Token konnte nicht gespeichert werden (Startskript lehnt ihn ab)."
    else:
        speichern("CLAUDE_CODE_OAUTH_TOKEN", token)
    return "🔑 Claude-Token gespeichert, deine Nachricht ist gelöscht. " + status()
