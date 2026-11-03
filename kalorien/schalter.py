"""Kalorien-App - Registrierung ein-/ausschalten ohne Neustart und ohne Server-Login.

Die Datei data/kalorien_registrierung.txt ("offen" oder "zu") hat Vorrang vor KALORIEN_OFFEN in der .env.
Fehlt die Datei, gilt die .env (Standard: offen). Gelesen wird bei jeder Registrierung - Aenderungen wirken sofort.
Gesetzt wird sie von Klaus per Telegram (/fit_registrierung an|aus, nur Nikola) auf demselben Server."""
from __future__ import annotations

import os
from pathlib import Path


def datei() -> Path:
    return Path(os.getenv("KALORIEN_SCHALTER") or Path(__file__).resolve().parent.parent / "data" / "kalorien_registrierung.txt")


def offen() -> bool:
    try:
        wert = datei().read_text(encoding="utf-8").strip().lower()
    except OSError:
        wert = ""
    if wert in ("offen", "zu"):
        return wert == "offen"
    return os.getenv("KALORIEN_OFFEN", "1").strip() != "0"


def setzen(an: bool) -> None:
    d = datei()
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text("offen" if an else "zu", encoding="utf-8")


def quelle() -> str:
    try:
        if datei().read_text(encoding="utf-8").strip().lower() in ("offen", "zu"):
            return "Schalter (Telegram)"
    except OSError:
        pass
    return "Einstellung KALORIEN_OFFEN in der .env"
