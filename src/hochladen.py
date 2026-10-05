"""
Klaus - Website-Entwuerfe auf den IONOS-Webspace hochladen (SFTP) und Briefe drucken

    hochladen.entwuerfe(token)   data/briefe/_hochladen/entwurf/<firma>/index.html  ->  <Webspace>/entwurf/<firma>/
    hochladen.drucken(token)     alle noch nicht gedruckten data/briefe/<firma>/brief.pdf an den Standarddrucker

Beides nur mit einem Token aus dem Freigabe-Gate (freigabe.anfragen) - ohne passiert nichts.

.env: KLESRO_SFTP_HOST, KLESRO_SFTP_USER, KLESRO_SFTP_PASS, KLESRO_SFTP_ORDNER, KLESRO_WEBSITE
"""

import os
import posixpath
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

import freigabe

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
BRIEFE = BASE_DIR / "data" / "briefe"
QUELLE = BRIEFE / "_hochladen"
HOST = os.getenv("KLESRO_SFTP_HOST", "").strip()
USER = os.getenv("KLESRO_SFTP_USER", "").strip()
PASSWORT = os.getenv("KLESRO_SFTP_PASS", "").strip()
ORDNER = os.getenv("KLESRO_SFTP_ORDNER", "/").strip() or "/"
WEBSITE = os.getenv("KLESRO_WEBSITE", "").strip().rstrip("/")


def eingerichtet() -> bool:
    return bool(HOST and USER and PASSWORT)


def _ordner_anlegen(sftp, pfad: str) -> None:
    teile = [t for t in pfad.split("/") if t]
    aktuell = "/" if pfad.startswith("/") else ""
    for teil in teile:
        aktuell = posixpath.join(aktuell, teil)
        try:
            sftp.stat(aktuell)
        except OSError:
            sftp.mkdir(aktuell)


def vor_hochladen() -> tuple[int, str | None]:
    """Was waere hochzuladen? -> (Anzahl, Hinderungsgrund oder None). Vor der Freigabe-Anfrage pruefen."""
    if not eingerichtet():
        return 0, "Der Webspace-Zugang fehlt: KLESRO_SFTP_HOST, KLESRO_SFTP_USER und KLESRO_SFTP_PASS in die .env eintragen."
    anzahl = len(list(QUELLE.glob("entwurf/*/index.html")))
    return anzahl, None if anzahl else "Es gibt noch keine Entwürfe zum Hochladen. Erst Briefe erstellen."


def entwuerfe(token: str | None) -> str:
    """Laedt alle Entwuerfe hoch (nur mit Freigabe-Token) und prueft einen davon. Gibt eine Meldung fuer Klaus zurueck."""
    anzahl, grund = vor_hochladen()
    if grund:
        return grund
    freigabe.pruefe(token, "hochladen")
    dateien = sorted(QUELLE.glob("entwurf/*/index.html"))
    import paramiko

    verbindung = paramiko.Transport((HOST, 22))
    try:
        verbindung.connect(username=USER, password=PASSWORT)
        sftp = paramiko.SFTPClient.from_transport(verbindung)
        for datei in dateien:
            ziel = posixpath.join(ORDNER, "entwurf", datei.parent.name)
            _ordner_anlegen(sftp, ziel)
            sftp.put(str(datei), posixpath.join(ziel, "index.html"))
        sftp.close()
    finally:
        verbindung.close()

    # Stichprobe: ist der erste Entwurf wirklich unter der QR-Adresse erreichbar?
    if WEBSITE:
        url = f"{WEBSITE}/entwurf/{dateien[0].parent.name}/"
        try:
            ok = requests.get(url, timeout=15).status_code == 200
        except requests.RequestException:
            ok = False
        if not ok:
            return (f"{len(dateien)} Entwürfe hochgeladen, aber {url} ist nicht erreichbar. "
                    "Wahrscheinlich stimmt KLESRO_SFTP_ORDNER nicht (der Ordner, auf den die Domain zeigt).")
    return f"{len(dateien)} Entwürfe sind online, die QR-Codes funktionieren."


def zu_drucken(nur_neue: bool = True) -> list[Path]:
    pdfs = sorted(BRIEFE.glob("*/brief.pdf"))
    return [p for p in pdfs if not (p.parent / ".gedruckt").exists()] if nur_neue else pdfs


def drucken(token: str | None, nur_neue: bool = True) -> str:
    """Schickt die Brief-PDFs an den Windows-Standarddrucker (nur mit Freigabe-Token). Gedruckte werden markiert."""
    pdfs = zu_drucken(nur_neue)
    if not pdfs:
        return "Keine neuen Briefe zum Drucken."
    freigabe.pruefe(token, "drucken")
    for pdf in pdfs:
        os.startfile(str(pdf), "print")  # Standard-PDF-Programm druckt auf den Standarddrucker
        (pdf.parent / ".gedruckt").write_text(time.strftime("%d.%m.%Y %H:%M"), encoding="utf-8")
        time.sleep(3)  # Druckauftraege nicht gleichzeitig losschicken
    return f"{len(pdfs)} Briefe gehen an den Drucker. Danach nur noch falten, kuvertieren, Briefmarke drauf."
