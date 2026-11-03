"""Kalorien-App Fitness-Social: Profil, Folgen, Feed mit Foto (EXIF-Bereinigung), Likes, Training, Wasser, Gewicht, Serie, Rangliste."""
import base64
import io
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_kalorien import Basis  # noqa: E402  (setzt auch die Test-Datenbank)
from kalorien import db, sozial  # noqa: E402


def jpeg(exif: bool = False) -> bytes:
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 80, 80)).save(puffer, "JPEG")
    b = puffer.getvalue()
    if exif:   # gefaelschtes EXIF-Segment (APP1) mit GPS-Text direkt hinter dem Kopf einfuegen
        daten = b"Exif\x00\x00GPS:52.5N,13.4E" + b"0" * 40
        b = b[:2] + b"\xff\xe1" + (len(daten) + 2).to_bytes(2, "big") + daten + b[2:]
    return b


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


class TestBild(unittest.TestCase):
    def test_exif_wird_entfernt_und_bild_bleibt_gueltig(self):
        roh = jpeg(exif=True)
        self.assertIn(b"GPS:52.5N", roh)
        sauber = sozial.jpeg_bereinigen(roh)
        self.assertNotIn(b"GPS", sauber)
        from PIL import Image
        self.assertEqual(Image.open(io.BytesIO(sauber)).size, (40, 40))

    def test_kein_jpeg_wird_abgelehnt(self):
        for schlecht in (b"GIF89a" + b"0" * 600, b"\xff\xd8\xff" + b"nicht ordentlich", b"<script>alert(1)</script>" * 40):
            with self.assertRaises(sozial.SozialFehler):
                sozial.jpeg_bereinigen(schlecht)

    def test_bildname_nur_erlaubtes_muster(self):
        self.assertIsNone(sozial.bild_lesen("../kalorien.db"))
        self.assertIsNone(sozial.bild_lesen("a" * 24 + ".jpg"))


class TestSozial(Basis):
    def test_serie(self):
        t = date(2026, 3, 10)
        tage = {(t - timedelta(days=i)).isoformat() for i in (0, 1, 2, 4)}
        self.assertEqual(sozial.serie(tage, t), 3)
        self.assertEqual(sozial.serie({(t - timedelta(days=1)).isoformat()}, t), 1)   # heute noch offen, Serie lebt
        self.assertEqual(sozial.serie({(t - timedelta(days=3)).isoformat()}, t), 0)

    def test_feed_beitrag_mit_foto_like_kommentar(self):
        a, b = self.neu("Feed Anja"), self.neu("Feed Bernd")
        s, p = self.api("POST", "/api/beitrag", {"art": "fortschritt", "text": "−3 kg!", "bild": b64(jpeg(exif=True))}, a)
        self.assertEqual(s, 200, p)
        feed = self.api("GET", "/api/feed", token=b)[1]
        eintrag = next(x for x in feed if x["id"] == p["id"])
        self.assertTrue(eintrag["bild"].startswith("/bild/"))
        with __import__("urllib.request").request.urlopen(self.url + eintrag["bild"]) as r:
            self.assertNotIn(b"GPS", r.read())
        self.assertEqual(self.api("POST", f"/api/beitrag/{p['id']}/gefaellt", token=b)[1]["likes"], 1)
        self.assertEqual(self.api("POST", f"/api/beitrag/{p['id']}/gefaellt", token=b)[1]["likes"], 0)   # zweites Tippen nimmt zurueck
        self.api("POST", f"/api/beitrag/{p['id']}/kommentar", {"text": "Stark!"}, b)
        voll = self.api("GET", f"/api/beitrag/{p['id']}", token=a)[1]
        self.assertEqual(voll["kommentar_liste"][0]["name"], "Feed Bernd")
        self.assertEqual(voll["kommentare"], 1)

    def test_beitrag_loeschen_entfernt_datei_nur_fuer_besitzer(self):
        a, b = self.neu("Weg Anna"), self.neu("Weg Bob")
        _, p = self.api("POST", "/api/beitrag", {"text": "x", "bild": b64(jpeg())}, a)
        bild = self.api("GET", f"/api/beitrag/{p['id']}", token=a)[1]["bild"]
        self.assertEqual(self.api("POST", "/api/loeschen", {"art": "beitrag", "id": p["id"]}, b)[0], 403)
        self.assertEqual(self.api("POST", "/api/loeschen", {"art": "beitrag", "id": p["id"]}, a)[0], 200)
        self.assertFalse((db.BILDER / bild.split("/")[-1]).exists())

    def test_leerer_beitrag_und_zu_grosses_foto(self):
        a = self.neu("Leer Lea")
        self.assertEqual(self.api("POST", "/api/beitrag", {"text": ""}, a)[0], 400)
        self.assertEqual(self.api("POST", "/api/beitrag", {"text": "x", "bild": b64(b"\xff\xd8\xff" + b"0" * (1024 * 1024))}, a)[0], 400)

    def test_folgen_filtert_feed_und_blockieren_versteckt(self):
        a, b, c = self.neu("Folge Fia"), self.neu("Folge Finn"), self.neu("Folge Fred")
        self.api("POST", "/api/beitrag", {"text": "Beitrag von Finn"}, b)
        self.api("POST", "/api/beitrag", {"text": "Beitrag von Fred"}, c)
        self.assertEqual(self.api("GET", "/api/feed?art=folge", token=a)[1], [])
        self.api("POST", "/api/folgen", {"name": "Folge Finn"}, a)
        namen = {x["name"] for x in self.api("GET", "/api/feed?art=folge", token=a)[1]}
        self.assertEqual(namen, {"Folge Finn"})
        self.assertEqual(self.api("GET", "/api/profil/Folge%20Finn", token=a)[1]["folger"], 1)
        self.api("POST", "/api/blockieren", {"name": "Folge Fred"}, a)
        self.assertNotIn("Folge Fred", {x["name"] for x in self.api("GET", "/api/feed", token=a)[1]})

    def test_training_kcal_schaetzung_wasser_gewicht(self):
        t = self.neu("Fit Fabi")
        self.api("POST", "/api/gewicht", {"kg": 80, "datum": date.today().isoformat()}, t)
        s, tr = self.api("POST", "/api/training", {"art": "laufen", "minuten": 30}, t)
        self.assertEqual(s, 200)
        self.assertEqual(tr["kcal"], round(9.8 * 80 * 0.5))
        self.assertEqual(self.api("POST", "/api/training", {"art": "yoga", "minuten": 20, "kcal": 90}, t)[1]["kcal"], 90)
        self.assertEqual(self.api("POST", "/api/wasser", {"ml": 250}, t)[1]["ml"], 250)
        self.assertEqual(self.api("POST", "/api/wasser", {"ml": -1000}, t)[1]["ml"], 0)   # nie unter 0
        tag = self.api("GET", "/api/tag", token=t)[1]
        self.assertEqual(len(tag["training"]), 2)
        self.assertEqual(tag["verbrannt"], tr["kcal"] + 90)
        self.assertEqual(self.api("POST", "/api/gewicht", {"kg": 10}, t)[0], 400)
        self.assertEqual(self.api("POST", "/api/training", {"art": "laufen", "minuten": 0}, t)[0], 400)
        self.assertEqual(self.api("GET", "/api/profil/Fit%20Fabi", token=t)[1]["serie"], 1)

    def test_rangliste_deckelt_pro_tag_und_respektiert_opt_out(self):
        a, b = self.neu("Rang Rita"), self.neu("Rang Rolf")
        self.api("POST", "/api/training", {"art": "laufen", "minuten": 600}, a)    # 600 Min an einem Tag zaehlen nur 240
        self.api("POST", "/api/training", {"art": "laufen", "minuten": 30}, b)
        liste = {x["name"]: x for x in self.api("GET", "/api/rangliste", token=a)[1]}
        self.assertEqual(liste["Rang Rita"]["minuten"], 240)
        self.api("PUT", "/api/ich", {"rangliste": False}, b)
        self.assertNotIn("Rang Rolf", {x["name"] for x in self.api("GET", "/api/rangliste", token=a)[1]})

    def test_suche_und_bio(self):
        a, b = self.neu("Suche Sara"), self.neu("Suche Sven")
        self.api("PUT", "/api/ich", {"bio": "Läuferin aus Köln"}, a)
        self.assertEqual(self.api("GET", "/api/profil/Suche%20Sara", token=b)[1]["bio"], "Läuferin aus Köln")
        self.assertEqual([x["name"] for x in self.api("GET", "/api/suche?q=Suche%20Sa", token=b)[1]], ["Suche Sara"])
        self.assertEqual(self.api("GET", "/api/suche?q=%25", token=b)[1], [])
        self.assertEqual(self.api("GET", "/api/profil/Gibts%20nicht", token=b)[0], 404)

    def test_konto_loeschen_entfernt_beitragsfotos(self):
        a = self.neu("Foto Fritz")
        _, p = self.api("POST", "/api/beitrag", {"text": "x", "bild": b64(jpeg())}, a)
        datei = db.BILDER / self.api("GET", f"/api/beitrag/{p['id']}", token=a)[1]["bild"].split("/")[-1]
        self.assertTrue(datei.exists())
        self.api("DELETE", "/api/ich", token=a)
        self.assertFalse(datei.exists())


if __name__ == "__main__":
    unittest.main()
