"""
Klaus - Brief-Generator (ersetzt die Werbe-Mails)

Werbe-Mails an Firmen brauchen in Deutschland eine ausdrueckliche Einwilligung (UWG § 7) -
Briefe per Post nicht. Fuer jede Firma aus der Lead-Liste entsteht deshalb:
    data/briefe/<firma>/entwurf.html   ein Website-Entwurf nur fuer diese Firma
    data/briefe/<firma>/entwurf.png    Screenshot davon
    data/briefe/<firma>/brief.pdf      DIN-5008-Brief (Fensterkuvert) mit Entwurf und QR-Code

Nutzung:
    .venv/Scripts/python src/briefe.py                                # alle Leads aus data/leads.csv
    .venv/Scripts/python src/briefe.py --leads data/leads_sample.csv  # Testdaten
    .venv/Scripts/python src/briefe.py --nur 3 --ki claude            # erste 3, Text individuell von Claude

.env: KLESRO_ABSENDER_NAME, KLESRO_ABSENDER_FIRMA, KLESRO_ABSENDER_MAIL, KLESRO_ADRESSE, KLESRO_TELEFON, KLESRO_WEBSITE
"""

import argparse
import base64
import csv
import datetime as dt
import html
import io
import os
import re
import sys
from pathlib import Path

import qrcode
import qrcode.image.svg
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
VORLAGEN = Path(__file__).resolve().parent / "vorlagen"
AUSGABE = BASE_DIR / "data" / "briefe"

ABSENDER = {
    "name": os.getenv("KLESRO_ABSENDER_NAME", "").strip(),
    "firma": os.getenv("KLESRO_ABSENDER_FIRMA", "Klesro Web").strip(),
    "mail": os.getenv("KLESRO_ABSENDER_MAIL", "").strip(),
    "adresse": os.getenv("KLESRO_ADRESSE", "").strip(),
    "telefon": os.getenv("KLESRO_TELEFON", "").strip(),
    "website": os.getenv("KLESRO_WEBSITE", "").strip(),
}
ORT = os.getenv("KLAUS_ORT", "Göppingen").split(",")[0].strip()

# Branche -> Farbwelt, Symbol, Ueberschrift und typische Leistungen (allgemein gehalten, nichts Erfundenes ueber die Firma)
BRANCHEN = [
    (r"schrein|tischler|holz", dict(farbe="#b5651d", dunkel="#3b2414", hell="#f3dcc4", symbol="🪚", titel=("Handwerk aus", "Meisterhand"),
        untertitel="Möbel, Innenausbau und Reparaturen – individuell geplant und sauber umgesetzt.", knopf="Anfrage stellen",
        leistungen=[("🪑", "Möbelbau", "Maßgefertigte Möbel, die genau in Ihren Raum passen."),
                    ("🏠", "Innenausbau", "Türen, Treppen, Decken und Einbauten aus einer Hand."),
                    ("🔧", "Reparaturen", "Schnelle Hilfe, wenn etwas klemmt oder kaputt ist.")])),
    (r"kosmetik|nagel|beauty|wimper", dict(farbe="#d16b8f", dunkel="#4a1d2e", hell="#f8d9e4", symbol="💅", titel=("Zeit für", "dich"),
        untertitel="Professionelle Pflege in entspannter Atmosphäre – einfach online Termin anfragen.", knopf="Termin anfragen",
        leistungen=[("✨", "Gesichtspflege", "Behandlungen, abgestimmt auf Ihren Hauttyp."),
                    ("💅", "Nägel", "Maniküre, Pediküre und Nageldesign."),
                    ("🌿", "Wohlfühlen", "Kleine Auszeiten für zwischendurch.")])),
    (r"friseur|barber|haar", dict(farbe="#2f6f8f", dunkel="#132b38", hell="#d3e8f2", symbol="✂️", titel=("Ihr neuer", "Look"),
        untertitel="Schnitt, Farbe und Styling – mit Beratung, die zu Ihnen passt.", knopf="Termin anfragen",
        leistungen=[("✂️", "Schnitt", "Für Damen, Herren und Kinder."), ("🎨", "Farbe", "Von dezent bis auffällig."),
                    ("💈", "Styling", "Für den Alltag und besondere Anlässe.")])),
    (r"fahrrad|bike|e-bike", dict(farbe="#2e8b57", dunkel="#123a24", hell="#d4efdf", symbol="🚲", titel=("Bereit für die", "nächste Tour"),
        untertitel="Fahrräder, E-Bikes und Werkstatt – kompetent beraten, schnell repariert.", knopf="Werkstatt-Termin",
        leistungen=[("🚲", "Verkauf", "Räder und E-Bikes für jeden Zweck."), ("🛠️", "Werkstatt", "Inspektion und Reparatur."),
                    ("🔋", "E-Bike-Service", "Akku-Check und Software-Updates.")])),
    (r"maler|lackier", dict(farbe="#3a6ea5", dunkel="#14273d", hell="#d6e4f3", symbol="🎨", titel=("Frische Farbe für", "Ihr Zuhause"),
        untertitel="Innen- und Außenarbeiten, sauber und termingerecht.", knopf="Angebot anfragen",
        leistungen=[("🖌️", "Innenräume", "Wände, Decken, Lackierarbeiten."), ("🏡", "Fassade", "Schutz und Optik für außen."),
                    ("🧱", "Spachtel & Tapete", "Vom Untergrund bis zum Finish.")])),
    (r"garten|landschaft", dict(farbe="#4f8a2b", dunkel="#1e3410", hell="#dcefcd", symbol="🌳", titel=("Ihr Garten in", "besten Händen"),
        untertitel="Pflege, Gestaltung und Pflasterarbeiten rund ums Jahr.", knopf="Beratung anfragen",
        leistungen=[("🌿", "Gartenpflege", "Rasen, Hecken, Beete."), ("🪨", "Pflaster & Wege", "Terrassen und Einfahrten."),
                    ("🌸", "Gestaltung", "Neuanlagen nach Ihren Wünschen.")])),
    (r"metzger|fleisch", dict(farbe="#a33a2b", dunkel="#3d150f", hell="#f3d6d1", symbol="🥩", titel=("Qualität aus der", "Region"),
        untertitel="Frische Wurst- und Fleischwaren, Mittagstisch und Partyservice.", knopf="Vorbestellen",
        leistungen=[("🥩", "Frischfleisch", "Aus regionaler Herkunft."), ("🥪", "Mittagstisch", "Täglich wechselnde Gerichte."),
                    ("🎉", "Partyservice", "Für Feiern jeder Größe.")])),
    (r"physio|massage|therap", dict(farbe="#1f8a8a", dunkel="#0d3535", hell="#d0eeee", symbol="🧘", titel=("Bewegung ist", "Lebensqualität"),
        untertitel="Physiotherapie und Massagen – Termine einfach anfragen.", knopf="Termin anfragen",
        leistungen=[("💪", "Krankengymnastik", "Gezielt und individuell."), ("💆", "Massage", "Lockert und entspannt."),
                    ("🦵", "Manuelle Therapie", "Für Gelenke und Rücken.")])),
]
STANDARD_BRANCHE = dict(farbe="#e8672a", dunkel="#2a1a10", hell="#fbe1d3", symbol="⭐", titel=("Willkommen bei", "uns"),
    untertitel="Kompetent, zuverlässig und ganz in Ihrer Nähe.", knopf="Kontakt aufnehmen",
    leistungen=[("✅", "Beratung", "Wir nehmen uns Zeit für Ihr Anliegen."), ("🛠️", "Umsetzung", "Sorgfältig und termingerecht."),
                ("🤝", "Service", "Auch nach dem Auftrag für Sie da.")])


def branche(lead: dict) -> dict:
    text = f"{lead.get('name', '')} {lead.get('branche_suchbegriff', '')}".lower()
    return next((daten for muster, daten in BRANCHEN if re.search(muster, text)), STANDARD_BRANCHE)


def slugify(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:50] or "firma"


def fuellen(vorlage: str, werte: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(werte.get(m.group(1), "")), vorlage)


def fehlt(text: str, hinweis: str) -> str:
    return html.escape(text) if text else f'<span class="fehlt">[{hinweis} in .env eintragen]</span>'


# ------------------------------------------------------------------ Entwurf
def entwurf_html(lead: dict) -> str:
    b = branche(lead)
    e = {k: html.escape(str(v)) for k, v in lead.items() if isinstance(v, str)}
    name = e.get("name", "Ihre Firma")
    teile = name.split(" ", 1)
    bewertung = ""
    if lead.get("bewertung") and lead.get("anzahl_bewertungen"):
        bewertung = (f'<div class="karte"><b>★ {html.escape(lead["bewertung"]).replace(".", ",")}</b>'
                     f'{html.escape(lead["anzahl_bewertungen"])} Bewertungen bei Google</div>')
    leistungen = "".join(f'<div class="karte2"><i>{i}</i><b>{t}</b><p>{p}</p></div>' for i, t, p in b["leistungen"])
    ort = re.sub(r"^\d{5}\s*", "", lead.get("adresse", "").split(",")[-1].strip()) or ORT
    return fuellen((VORLAGEN / "entwurf.html").read_text(encoding="utf-8"), {
        **b, "name": name, "adresse": e.get("adresse", ""), "absender_firma": html.escape(ABSENDER["firma"]),
        "logo_vorne": teile[0] + (" " if len(teile) > 1 else ""), "logo_hinten": teile[1] if len(teile) > 1 else "",
        "titel_vorne": b["titel"][0], "titel_hinten": b["titel"][1], "ort_kurz": html.escape(ort),
        "bewertung_karte": bewertung, "leistungen": leistungen,
        "telefon_zeile": f'<div class="zeile">📞 {e["telefon"]}</div>' if e.get("telefon") else "",
    })


# ------------------------------------------------------------------ Brieftext
def _ki_auftrag(lead: dict, bewertung: str) -> str:
    name = lead.get("name", "Ihre Firma")
    return f"""Schreibe den Text eines kurzen Geschaeftsbriefs an die Firma "{name}" ({lead.get('branche_suchbegriff', '')}).
Absender: {ABSENDER['name']} von {ABSENDER['firma']}, Webdesign aus der Region.
Fakten, die du verwenden darfst (sonst NICHTS erfinden): Die Firma hat online keine eigene Website. {('Sie hat ' + bewertung + '.') if bewertung else ''}
Dem Brief liegt ein unverbindlicher Website-Entwurf nur fuer diese Firma bei (siehe Bild unten, QR-Code).
Ziel: ein kurzes, kostenloses Gespraech vorschlagen. Keine Preise, keine Versprechen, kein Druck.
Form: Sie-Form, natuerliches Deutsch mit korrekten Umlauten (ä, ö, ü) und ß, 3 kurze Absaetze, insgesamt 90 bis 130 Woerter. Beginne mit "Sehr geehrte Damen und Herren,".
Ohne Betreff, ohne Grussformel, ohne Unterschrift. Absaetze durch eine Leerzeile trennen. Gib NUR den Brieftext aus."""


def _ki_text(auftrag: str, ki: str) -> str:
    if ki == "claude":
        import shutil
        import subprocess

        claude = shutil.which("claude")
        if claude:
            ergebnis = subprocess.run([claude, "-p", auftrag, "--model", "sonnet"], capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            text = ergebnis.stdout.strip()
            if ergebnis.returncode == 0 and len(text) > 200 and "limit" not in text.lower()[:200]:
                return text
            print(f"  Claude nicht verfuegbar ({text[:80]!r}) - Gemini schreibt.")
        ki = "gemini"
    if ki == "gemini":
        import recherche

        try:
            return recherche.gemini(auftrag, "Du schreibst hoefliche, klare deutsche Geschaeftsbriefe.")
        except recherche.KeineKI as e:
            print(f"  Gemini nicht verfuegbar ({e}) - Ollama schreibt.")
    import llm

    if not llm.ist_verfuegbar():
        raise RuntimeError("Ollama laeuft nicht")
    return llm.frage(auftrag, system="Du schreibst hoefliche, klare deutsche Geschaeftsbriefe.", temperatur=0.5)


def brief_text(lead: dict, ki: str = "aus") -> str:
    """Drei kurze Absaetze. ki: "aus" (Standardtext), "lokal" (Ollama), "gemini" oder "claude" (faellt auf Gemini zurueck)."""
    name = lead.get("name", "Ihre Firma")
    bewertung = ""
    if lead.get("bewertung") and lead.get("anzahl_bewertungen"):
        bewertung = f"{lead['bewertung'].replace('.', ',')} Sterne bei {lead['anzahl_bewertungen']} Google-Bewertungen"
    if ki != "aus":
        try:
            text = _ki_text(_ki_auftrag(lead, bewertung), ki)
            # Nachkontrolle: Gruss, Unterschrift und Betreff kommen aus der Vorlage
            absaetze = [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()
                        and not re.match(r"(mit freundlichen|viele gr|beste gr|betreff)", a.strip(), re.I)
                        and ABSENDER["name"] not in a]
            if 2 <= len(absaetze) <= 5 and absaetze[0].startswith("Sehr geehrte"):
                return "".join(f"<p>{html.escape(a)}</p>" for a in absaetze)
            print("  KI-Text hatte nicht die richtige Form - nehme Standardtext.")
        except Exception as fehler:
            print(f"  KI-Text nicht moeglich ({fehler}) - nehme Standardtext.")
    zusatz = f" Ihre {bewertung} zeigen, dass Ihre Kunden zufrieden sind." if bewertung else ""
    return "".join(f"<p>{html.escape(a)}</p>" for a in [
        "Sehr geehrte Damen und Herren,",
        f"bei der Suche nach Betrieben in unserer Region ist mir aufgefallen, dass {name} noch keine eigene Website hat.{zusatz} "
        "Viele Menschen suchen heute zuerst online nach Öffnungszeiten, Leistungen und Kontakt – dort sind Sie bisher kaum zu finden.",
        "Deshalb habe ich Ihnen unverbindlich einen ersten Entwurf erstellt, wie Ihre Website aussehen könnte. "
        "Sie sehen ihn unten auf diesem Brief oder über den QR-Code.",
        "Wenn Ihnen der Entwurf gefällt, besprechen wir gern in einem kurzen, kostenlosen Gespräch, was Ihnen wichtig ist. "
        "Ein Anruf oder eine kurze Mail genügt.",
    ])


def qr_svg(url: str) -> str:
    bild = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    puffer = io.BytesIO()
    bild.save(puffer)
    return re.sub(r"<\?xml[^>]*\?>", "", puffer.getvalue().decode("utf-8"))


def brief_html(lead: dict, bild_png: bytes, text: str) -> str:
    a = ABSENDER
    adresse_teile = [t.strip() for t in a["adresse"].split(",") if t.strip()]
    marke = a["firma"].split(" ", 1)
    empfaenger = "<br>".join(html.escape(t.strip()) for t in [lead.get("name", "")] + lead.get("adresse", "").split(",") if t.strip())
    website = a["website"] or ""
    ziel = f"{website.rstrip('/')}/entwurf/{slugify(lead.get('name', ''))}/" if website else ""
    return fuellen((VORLAGEN / "brief.html").read_text(encoding="utf-8"), {
        "name": html.escape(lead.get("name", "")),
        "marke_vorne": html.escape(marke[0] + (" " if len(marke) > 1 else "")), "marke_hinten": html.escape(marke[1] if len(marke) > 1 else ""),
        "absender_name": fehlt(a["name"], "KLESRO_ABSENDER_NAME"), "absender_firma": html.escape(a["firma"]),
        "absender_mail": fehlt(a["mail"], "KLESRO_ABSENDER_MAIL"), "absender_telefon": fehlt(a["telefon"], "KLESRO_TELEFON"),
        "absender_website": html.escape(website.removeprefix("https://")),
        "absender_adresse_zeilen": "<br>".join(html.escape(t) for t in adresse_teile) or fehlt("", "KLESRO_ADRESSE"),
        "absender_adresse_einzeilig": html.escape(", ".join(adresse_teile)) or fehlt("", "KLESRO_ADRESSE"),
        "empfaenger": empfaenger, "ort": html.escape(ORT), "datum": f"{dt.date.today():%d.%m.%Y}",
        "betreff": f"Ein Website-Entwurf für {html.escape(lead.get('name', ''))}",
        "text": text, "bild": "data:image/png;base64," + base64.b64encode(bild_png).decode(),
        "qr": qr_svg(ziel) if ziel else fehlt("", "KLESRO_WEBSITE"),
    })


# ------------------------------------------------------------------ Ablauf (Qt rendert Screenshot und PDF)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leads", default=str(BASE_DIR / "data" / "leads.csv"))
    ap.add_argument("--nur", type=int, default=0, help="nur die ersten N Leads")
    ap.add_argument("--ki", choices=["aus", "lokal", "gemini", "claude"], default="aus",
                    help="Brieftext: Standardvorlage (aus), lokales Modell oder Claude (beste Qualitaet)")
    args = ap.parse_args()

    with open(args.leads, newline="", encoding="utf-8") as f:
        leads = [r for r in csv.DictReader(f) if r.get("name", "").strip()]
    if args.nur:
        leads = leads[: args.nur]
    if not leads:
        print(f"Keine Leads in {args.leads}.")
        return

    from PySide6.QtCore import QMarginsF, QRect, QTimer, QUrl
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    ansicht = QWebEngineView()
    ansicht.resize(1280, 860)
    ansicht.move(-4000, -4000)  # ausserhalb des Bildschirms rendern
    ansicht.show()
    druck = QWebEnginePage()
    layout = QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0))
    warteschlange = list(leads)
    fertig = []

    def naechster() -> None:
        if not warteschlange:
            print(f"\nFertig: {len(fertig)} Briefe in {AUSGABE}")
            print(f"Hochladen: Inhalt von {AUSGABE / '_hochladen'} auf {ABSENDER['website'] or 'deine Website'} kopieren")
            for pfad in fertig:
                print(f"  {pfad}")
            app.quit()
            return
        lead = warteschlange.pop(0)
        ordner = AUSGABE / slugify(lead["name"])
        ordner.mkdir(parents=True, exist_ok=True)
        print(f"- {lead['name']}: Entwurf …", flush=True)
        seite = entwurf_html(lead)
        (ordner / "entwurf.html").write_text(seite, encoding="utf-8")

        def nach_laden(_ok: bool) -> None:
            ansicht.loadFinished.disconnect(nach_laden)
            QTimer.singleShot(700, lambda: screenshot(lead, ordner))

        ansicht.loadFinished.connect(nach_laden)
        ansicht.setHtml(seite, QUrl.fromLocalFile(str(ordner) + "/"))

    def screenshot(lead: dict, ordner: Path) -> None:
        ansicht.grab(QRect(0, 0, 1280, 600)).save(str(ordner / "entwurf.png"))  # Kopf + Hauptbereich
        # Upload-Ordner: einmal auf den Webspace kopieren, dann oeffnet jeder QR-Code "seinen" Entwurf
        web = AUSGABE / "_hochladen" / "entwurf" / ordner.name
        web.mkdir(parents=True, exist_ok=True)
        (web / "index.html").write_text((ordner / "entwurf.html").read_text(encoding="utf-8"), encoding="utf-8")
        png = (ordner / "entwurf.png").read_bytes()
        print("  Brieftext …", flush=True)
        brief = brief_html(lead, png, brief_text(lead, ki=args.ki))
        (ordner / "brief.html").write_text(brief, encoding="utf-8")

        def nach_brief(_ok: bool) -> None:
            druck.loadFinished.disconnect(nach_brief)
            druck.printToPdf(str(ordner / "brief.pdf"), layout)

        druck.loadFinished.connect(nach_brief)
        druck.setHtml(brief, QUrl.fromLocalFile(str(ordner) + "/"))

    def pdf_fertig(pfad: str, ok: bool) -> None:
        print(f"  PDF {'ok' if ok else 'FEHLER'}: {pfad}", flush=True)
        if ok:
            fertig.append(pfad)
        naechster()

    druck.pdfPrintingFinished.connect(pdf_fertig)
    QTimer.singleShot(0, naechster)
    app.exec()


if __name__ == "__main__":
    main()
