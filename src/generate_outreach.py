"""
Klaus - Erstkontakt-Entwuerfe (Mail)

ACHTUNG: Werbe-Mails an Firmen brauchen eine ausdrueckliche Einwilligung (UWG § 7) - NICHT fuer
Erstkontakte verwenden, sondern src/briefe.py (Briefe per Post sind erlaubt).

Liest data/leads.csv und erzeugt fuer jede Firma einen kurzen, personalisierten
Text-Entwurf in data/outreach/<firma>.txt.

Nutzung:
    python src/generate_outreach.py                 # feste Vorlage
    python src/generate_outreach.py --ai            # lokale KI (Ollama) bewertet + schreibt
    python src/generate_outreach.py --ai --leads data/leads_sample.csv
"""

import argparse
import csv
import os
import re
from pathlib import Path

from dotenv import load_dotenv

import llm

load_dotenv()

ABSENDER_NAME = os.getenv("KLESRO_ABSENDER_NAME", "Nikola Georgiev")
ABSENDER_FIRMA = os.getenv("KLESRO_ABSENDER_FIRMA", "Klesro Web")
ABSENDER_MAIL = os.getenv("KLESRO_ABSENDER_MAIL", "info@klesro-web.de")

BASE_DIR = Path(__file__).resolve().parent.parent
LEADS_PATH = BASE_DIR / "data" / "leads.csv"
OUT_DIR = BASE_DIR / "data" / "outreach"

VORLAGE = """Betreff: Kurze Frage zu {name}

Hallo,

kurz und unkompliziert: Ich bin {absender_name} von {absender_firma}
({absender_mail}) und baue Websites fuer Betriebe hier in der Region.

Mir ist aufgefallen, dass {name} noch keine eigene Website hat - dabei
suchen viele Kunden vorher online nach Oeffnungszeiten, Adresse oder Preisen.

Ich mache dazu gerne einen kostenlosen, unverbindlichen Vorschlag, wie eine
einfache Seite fuer Sie aussehen koennte. Interesse? Ein kurzer Rueckruf
oder eine Antwort auf diese Mail reicht.

Viele Gruesse
{absender_name}
{absender_firma}
{absender_mail}

---
Adresse: {adresse}
Telefon: {telefon}
Google Maps: {maps_link}
"""


NL = chr(10)

SYSTEM = (
    "Du bist Klaus, ein interner Assistent und schreibst Mails im Namen von " + ABSENDER_NAME + " (Klesro Web, "
    "kleiner Webdesign-Betrieb im Raum Goeppingen). Schreibe in Ich-Form als " + ABSENDER_NAME + ", "
    "erwaehne nie, dass du eine KI oder ein Assistent bist. Du schreibst auf Deutsch, freundlich, direkt, ohne Floskeln und "
    "ohne uebertriebene Versprechen. Du erfindest keine Fakten ueber die Firma."
)


def analysiere(row: dict) -> dict:
    """KI-Bewertung: lohnt sich der Kontakt, und welcher Aufhaenger passt?"""
    prompt = f"""Bewerte diesen Firmen-Lead (hat keine Website):
Name: {row.get('name')}
Suchbegriff/Branche: {row.get('branche_suchbegriff')}
Adresse: {row.get('adresse')}
Telefon: {row.get('telefon') or 'unbekannt'}
Google-Bewertung: {row.get('bewertung') or '?'} bei {row.get('anzahl_bewertungen') or '?'} Bewertungen

Antworte als JSON mit den Feldern:
"score" (1-10, wie gut passt die Firma als Kunde: aktive Firma, gute Bewertungen, Branche profitiert von Website),
"begruendung" (ein Satz),
"aufhaenger" (ein konkreter, wahrer Ansatzpunkt fuer die erste Mail, nur aus den Daten oben)."""
    return llm.frage(prompt, system=SYSTEM, als_json=True)


def schreibe_mail(row: dict, analyse: dict) -> str:
    prompt = f"""Schreibe eine kurze Erstkontakt-Mail (max. 100 Woerter) an die Firma "{row.get('name')}".
Firmenname exakt so uebernehmen: {row.get('name')}
Ziel: kostenlosen, unverbindlichen Website-Vorschlag anbieten.
Aufhaenger: {analyse.get('aufhaenger')}
Beginne mit "Betreff: ..." und dann der Mail. Unterschrift:
{ABSENDER_NAME}, {ABSENDER_FIRMA}, {ABSENDER_MAIL}"""
    return llm.frage(prompt, system=SYSTEM, temperatur=0.6)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "firma"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", action="store_true", help="lokale KI (Ollama) nutzen")
    ap.add_argument("--leads", default=str(LEADS_PATH), help="Pfad zur Lead-CSV")
    args = ap.parse_args()
    leads_path = Path(args.leads)

    if not leads_path.exists():
        print(f"Keine Leads gefunden unter {leads_path}. Erst search_leads.py ausfuehren.")
        return

    use_ai = args.ai
    if use_ai and not llm.ist_verfuegbar():
        print(f"Ollama/Modell '{llm.OLLAMA_MODEL}' nicht erreichbar - nutze feste Vorlage.")
        use_ai = False

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    anzahl = 0
    with open(leads_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue
            text = None
            if use_ai:
                try:
                    a = analysiere(row)
                    mail = schreibe_mail(row, a)
                    text = NL.join([
                        f"[KI-Score {a.get('score')}/10 - {a.get('begruendung')}]",
                        "",
                        mail,
                        "",
                        "---",
                        f"Adresse: {row.get('adresse', '')}",
                        f"Telefon: {row.get('telefon', '')}",
                        f"Google Maps: {row.get('maps_link', '')}",
                        "",
                    ])
                    print(f"  {name}: Score {a.get('score')}")
                except Exception as e:  # KI-Fehler darf den Lauf nicht stoppen
                    print(f"  ! KI-Fehler bei {name} ({e}) - nutze Vorlage.")
            if text is None:
                text = VORLAGE.format(
                name=name,
                adresse=row.get("adresse", ""),
                telefon=row.get("telefon", ""),
                maps_link=row.get("maps_link", ""),
                absender_name=ABSENDER_NAME,
                absender_firma=ABSENDER_FIRMA,
                absender_mail=ABSENDER_MAIL,
            )
            out_path = OUT_DIR / f"{slugify(name)}.txt"
            out_path.write_text(text, encoding="utf-8")
            anzahl += 1

    print(f"Fertig: {anzahl} Entwuerfe in {OUT_DIR} erstellt.")


if __name__ == "__main__":
    main()
