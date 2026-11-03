"""Kalorien-App - Datenbank (SQLite, eine Datei). Konten, Tagebuch, Forum, Chat, Meldungen."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

DATEI = Path(os.getenv("KALORIEN_DB") or Path(__file__).resolve().parent.parent / "data" / "kalorien.db")
BILDER = DATEI.parent / "kalorien_bilder"   # Beitragsfotos (nur hier, nie das Essens-Foto zur Schaetzung)
VIDEOS = DATEI.parent / "kalorien_videos"   # Reels (nach der Umwandlung in H.264/MP4) und das Rohmaterial waehrend der Verarbeitung

SCHEMA = """
CREATE TABLE IF NOT EXISTS nutzer (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE NOT NULL, pw_hash TEXT NOT NULL, salz TEXT NOT NULL,
    erstellt INTEGER NOT NULL, ziel_kcal INTEGER DEFAULT 2000, ziel_eiweiss INTEGER DEFAULT 100,
    ziel_kh INTEGER DEFAULT 250, ziel_fett INTEGER DEFAULT 65, profil TEXT DEFAULT '{}', gesperrt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS zugang (
    hash TEXT PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, art TEXT NOT NULL,
    name TEXT DEFAULT '', erstellt INTEGER NOT NULL, zuletzt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS eintrag (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, datum TEXT NOT NULL,
    mahlzeit TEXT NOT NULL, name TEXT NOT NULL, menge TEXT DEFAULT '', kcal REAL NOT NULL, eiweiss REAL DEFAULT 0,
    kh REAL DEFAULT 0, fett REAL DEFAULT 0, quelle TEXT DEFAULT 'hand', erstellt INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS eintrag_tag ON eintrag(nutzer, datum);
CREATE TABLE IF NOT EXISTS ki_nutzung (nutzer INTEGER NOT NULL, tag TEXT NOT NULL, n INTEGER DEFAULT 0, PRIMARY KEY (nutzer, tag));
CREATE TABLE IF NOT EXISTS thema (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, titel TEXT NOT NULL,
    text TEXT NOT NULL, erstellt INTEGER NOT NULL, letzte INTEGER NOT NULL, antworten INTEGER DEFAULT 0, versteckt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS antwort (
    id INTEGER PRIMARY KEY, thema INTEGER NOT NULL REFERENCES thema(id) ON DELETE CASCADE,
    nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, text TEXT NOT NULL, erstellt INTEGER NOT NULL, versteckt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, text TEXT NOT NULL,
    erstellt INTEGER NOT NULL, versteckt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS meldung (
    id INTEGER PRIMARY KEY, von INTEGER, art TEXT NOT NULL, ziel INTEGER NOT NULL, grund TEXT DEFAULT '', erstellt INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS folgen (
    von INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, ziel INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE,
    erstellt INTEGER NOT NULL, PRIMARY KEY (von, ziel));
CREATE TABLE IF NOT EXISTS beitrag (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, art TEXT NOT NULL,
    text TEXT DEFAULT '', bild TEXT DEFAULT '', erstellt INTEGER NOT NULL, versteckt INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS beitrag_zeit ON beitrag(erstellt);
CREATE TABLE IF NOT EXISTS gefaellt (
    beitrag INTEGER NOT NULL REFERENCES beitrag(id) ON DELETE CASCADE, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE,
    PRIMARY KEY (beitrag, nutzer));
CREATE TABLE IF NOT EXISTS kommentar (
    id INTEGER PRIMARY KEY, beitrag INTEGER NOT NULL REFERENCES beitrag(id) ON DELETE CASCADE,
    nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, text TEXT NOT NULL, erstellt INTEGER NOT NULL, versteckt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS training (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, datum TEXT NOT NULL,
    art TEXT NOT NULL, minuten INTEGER NOT NULL, kcal INTEGER NOT NULL, notiz TEXT DEFAULT '', erstellt INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS training_tag ON training(nutzer, datum);
CREATE TABLE IF NOT EXISTS wasser (nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, datum TEXT NOT NULL, ml INTEGER DEFAULT 0,
    PRIMARY KEY (nutzer, datum));
CREATE TABLE IF NOT EXISTS schritte (nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, datum TEXT NOT NULL, schritte INTEGER NOT NULL,
    quelle TEXT DEFAULT 'hand', PRIMARY KEY (nutzer, datum));
CREATE TABLE IF NOT EXISTS gewicht (nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, datum TEXT NOT NULL, kg REAL NOT NULL,
    PRIMARY KEY (nutzer, datum));
CREATE TABLE IF NOT EXISTS blockiert (nutzer INTEGER NOT NULL, ziel INTEGER NOT NULL, PRIMARY KEY (nutzer, ziel));
CREATE TABLE IF NOT EXISTS nutzer_ki (
    nutzer INTEGER PRIMARY KEY REFERENCES nutzer(id) ON DELETE CASCADE, anbieter TEXT NOT NULL, schluessel TEXT NOT NULL,
    modell TEXT DEFAULT '', erstellt INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pro_code (
    code TEXT PRIMARY KEY, tage INTEGER NOT NULL, erstellt INTEGER NOT NULL, benutzt_von INTEGER, benutzt_am INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS rezept (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, titel TEXT NOT NULL,
    beschreibung TEXT DEFAULT '', portionen INTEGER DEFAULT 1, zeit_min INTEGER DEFAULT 0, zutaten TEXT DEFAULT '[]',
    schritte TEXT DEFAULT '[]', kcal REAL DEFAULT 0, eiweiss REAL DEFAULT 0, kh REAL DEFAULT 0, fett REAL DEFAULT 0,
    tags TEXT DEFAULT '', bild TEXT DEFAULT '', oeffentlich INTEGER DEFAULT 0, offiziell INTEGER DEFAULT 0,
    erstellt INTEGER NOT NULL, versteckt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS rezept_gespeichert (
    nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, rezept INTEGER NOT NULL REFERENCES rezept(id) ON DELETE CASCADE,
    PRIMARY KEY (nutzer, rezept));
CREATE TABLE IF NOT EXISTS workout (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, datum TEXT NOT NULL, name TEXT NOT NULL,
    minuten INTEGER DEFAULT 0, kcal INTEGER DEFAULT 0, volumen REAL DEFAULT 0, notiz TEXT DEFAULT '', training_id INTEGER DEFAULT 0,
    erstellt INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS workout_tag ON workout(nutzer, datum);
CREATE TABLE IF NOT EXISTS satz (
    id INTEGER PRIMARY KEY, workout INTEGER NOT NULL REFERENCES workout(id) ON DELETE CASCADE,
    nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, uebung TEXT NOT NULL COLLATE NOCASE, nr INTEGER NOT NULL,
    wdh INTEGER NOT NULL, kg REAL NOT NULL);
CREATE INDEX IF NOT EXISTS satz_uebung ON satz(nutzer, uebung);
CREATE TABLE IF NOT EXISTS routine (
    id INTEGER PRIMARY KEY, nutzer INTEGER NOT NULL REFERENCES nutzer(id) ON DELETE CASCADE, name TEXT NOT NULL,
    uebungen TEXT NOT NULL DEFAULT '[]', erstellt INTEGER NOT NULL);
"""


def verbinden() -> sqlite3.Connection:
    DATEI.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATEI, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    spalten = {r["name"] for r in c.execute("PRAGMA table_info(nutzer)")}
    for name, ddl in (("bio", "TEXT DEFAULT ''"), ("in_rangliste", "INTEGER DEFAULT 1"), ("pro_bis", "INTEGER DEFAULT 0")):   # aeltere Datenbanken nachruesten
        if name not in spalten:
            c.execute(f"ALTER TABLE nutzer ADD COLUMN {name} {ddl}")
    spalten = {r["name"] for r in c.execute("PRAGMA table_info(beitrag)")}
    for name, ddl in (("video", "TEXT DEFAULT ''"), ("poster", "TEXT DEFAULT ''"), ("status", "TEXT DEFAULT 'fertig'"),
                      ("dauer", "REAL DEFAULT 0"), ("roh", "TEXT DEFAULT ''")):   # Reels sind Beitraege mit Video
        if name not in spalten:
            c.execute(f"ALTER TABLE beitrag ADD COLUMN {name} {ddl}")
    c.execute("CREATE INDEX IF NOT EXISTS beitrag_video ON beitrag(video, erstellt)")
    try:
        os.chmod(DATEI, 0o600)
    except OSError:
        pass
    return c


def pw_hash(passwort: str, salz: str) -> str:
    return hashlib.scrypt(passwort.encode(), salt=bytes.fromhex(salz), n=2 ** 14, r=8, p=1, dklen=32).hex()


def pw_stimmt(passwort: str, salz: str, soll: str) -> bool:
    return hmac.compare_digest(pw_hash(passwort, salz), soll)


def neues_salz() -> str:
    return secrets.token_hex(16)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def jetzt() -> int:
    return int(time.time())
