"""Vitamine, Mineralstoffe, Ballaststoffe, Zucker, Salz: Katalog, KI-Antwort, Barcode, Speichern, Tagessumme, Export, Datenbank-Nachruestung."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_kalorien import Basis  # noqa: E402  (setzt die Test-Datenbank)
from kalorien import db, ki, mikro, nahrung  # noqa: E402


class TestKatalog(unittest.TestCase):
    def test_bereinigen_behaelt_nur_bekannte_plausible_werte(self):
        r = mikro.bereinigen({"vitamin_c": "12,5", "eisen": 3, "quatsch": 5, "calcium": -4, "zink": "viel", "salz": 0, "vitamin_d": 99999, "kalium": float("nan")})
        self.assertEqual(r, {"vitamin_c": 12.5, "eisen": 3.0})
        self.assertEqual(mikro.bereinigen(None), {})
        self.assertEqual(mikro.bereinigen("kein dict"), {})

    def test_laden_ist_tolerant(self):
        self.assertEqual(mikro.laden('{"vitamin_c": 5}'), {"vitamin_c": 5.0})
        self.assertEqual(mikro.laden("kaputt{"), {})
        self.assertEqual(mikro.laden(None), {})
        self.assertEqual(mikro.laden({"calcium": 100}), {"calcium": 100.0})

    def test_summe(self):
        self.assertEqual(mikro.summe([{"vitamin_c": 10, "eisen": 1}, {"vitamin_c": 5.5}, {}, None]), {"vitamin_c": 15.5, "eisen": 1.0})

    def test_open_food_facts_einheiten_werden_umgerechnet(self):
        # OFF: alles in Gramm je 100 g. 0.0053 g Vitamin C = 5,3 mg; 0.00000015 g Vitamin D = 0,15 ug; 0.12 g Calcium = 120 mg
        r = mikro.aus_off({"vitamin-c_100g": 0.0053, "vitamin-d_100g": 0.00000015, "calcium_100g": 0.12, "fiber_100g": 6.2, "salt_100g": 1.1,
                           "sugars_100g": 4.5, "iron_100g": 0.0021, "vitamin-b12_100g": 0.0000024})
        self.assertAlmostEqual(r["vitamin_c"], 5.3, places=2)
        self.assertAlmostEqual(r["vitamin_d"], 0.15, places=2)
        self.assertAlmostEqual(r["calcium"], 120.0, places=1)
        self.assertAlmostEqual(r["eisen"], 2.1, places=2)
        self.assertAlmostEqual(r["vitamin_b12"], 2.4, places=2)
        self.assertEqual((r["ballaststoffe"], r["salz"], r["zucker"]), (6.2, 1.1, 4.5))
        self.assertEqual(mikro.aus_off({}), {})

    def test_katalog_ist_stimmig(self):
        schluessel = [e["key"] for e in mikro.KATALOG]
        self.assertEqual(len(schluessel), len(set(schluessel)))
        for e in mikro.KATALOG:
            self.assertIn(e["art"], ("mind", "max"))
            self.assertGreater(e["ziel"], 0)
            self.assertLess(e["ziel"], e["max"])
        oeffentlich = mikro.katalog_oeffentlich()
        self.assertNotIn("off", oeffentlich[0])
        self.assertIn("vitamin_c (mg)", mikro.fuer_ki())


class TestKiAntwort(unittest.TestCase):
    def test_lesen_nimmt_mikro_mit_und_bereinigt(self):
        r = ki.lesen(json.dumps({"gerichte": [{"name": "Orange", "menge": "1 Stück", "kcal": 60, "eiweiss": 1, "kh": 14, "fett": 0.2,
                                               "mikro": {"vitamin_c": "70", "ballaststoffe": 2.4, "unsinn": 5, "calcium": 9999999}}]}))
        self.assertEqual(r["gerichte"][0]["mikro"], {"vitamin_c": 70.0, "ballaststoffe": 2.4})

    def test_ohne_mikro_bleibt_alles_wie_vorher(self):
        r = ki.lesen('{"gerichte":[{"name":"Brot","kcal":100}]}')
        self.assertEqual(r["gerichte"][0]["mikro"], {})

    def test_anweisung_nennt_schluessel_mit_einheiten(self):
        self.assertIn("vitamin_c (mg)", ki.FORMAT)
        self.assertIn("mikro", ki.FORMAT)


class TestBarcodeMikro(unittest.TestCase):
    def test_barcode_liefert_mikro_je_100g(self):
        antwort = json.dumps({"status": 1, "product": {"product_name": "Haferflocken", "nutriments": {
            "energy-kcal_100g": 370, "proteins_100g": 13, "carbohydrates_100g": 59, "fat_100g": 7, "fiber_100g": 10, "iron_100g": 0.0044, "salt_100g": 0.02}}})

        class Fake:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return antwort.encode()
        with mock.patch("urllib.request.urlopen", return_value=Fake()):
            p = nahrung.barcode_suchen("4000000000001")
        self.assertEqual(p["mikro100"]["ballaststoffe"], 10.0)
        self.assertAlmostEqual(p["mikro100"]["eisen"], 4.4, places=2)


class TestSpeichernUndSumme(Basis):
    def test_eintrag_mit_mikro_tagessumme_export_und_katalog(self):
        t = self.neu("Mikro Mia")
        self.api("POST", "/api/eintrag", {"name": "Orange", "kcal": 60, "datum": "2026-02-01", "mikro": {"vitamin_c": 70, "ballaststoffe": 2.4, "blabla": 1}}, t)
        self.api("POST", "/api/eintrag", {"name": "Spinat", "kcal": 25, "datum": "2026-02-01", "mikro": {"vitamin_c": 28, "eisen": 3.6}}, t)
        self.api("POST", "/api/eintrag", {"name": "Wasser", "kcal": 0, "datum": "2026-02-01"}, t)      # ohne Mikro: geht weiter
        tag = self.api("GET", "/api/tag?datum=2026-02-01", token=t)[1]
        self.assertEqual(tag["mikro_summe"], {"vitamin_c": 98.0, "ballaststoffe": 2.4, "eisen": 3.6})
        orange = next(e for e in tag["eintraege"] if e["name"] == "Orange")
        self.assertEqual(orange["mikro"], {"vitamin_c": 70.0, "ballaststoffe": 2.4})     # Unbekanntes wurde nicht gespeichert
        self.assertEqual(next(e for e in tag["eintraege"] if e["name"] == "Wasser")["mikro"], {})
        katalog = self.api("GET", "/api/ich", token=t)[1]["mikro_katalog"]
        self.assertTrue(any(k["key"] == "vitamin_c" and k["einheit"] == "mg" for k in katalog))
        export = self.api("GET", "/api/export", token=t)[1]
        self.assertEqual(next(e for e in export["tagebuch"] if e["name"] == "Spinat")["mikro"], {"vitamin_c": 28.0, "eisen": 3.6})

    def test_eintrag_bearbeiten_behaelt_mikro(self):
        t = self.neu("Mikro Max")
        _, e = self.api("POST", "/api/eintrag", {"name": "Banane", "kcal": 100, "datum": "2026-02-02", "mikro": {"kalium": 420}}, t)
        s, _ = self.api("PUT", f"/api/eintrag/{e['id']}", {"name": "Banane groß", "kcal": 120, "mahlzeit": "snack"}, t)
        self.assertEqual(s, 200)
        eintrag = self.api("GET", "/api/tag?datum=2026-02-02", token=t)[1]["eintraege"][0]
        self.assertEqual(eintrag["name"], "Banane groß")
        self.assertEqual(eintrag["mikro"], {"kalium": 420.0})

    def test_kaputtes_mikro_im_body_bricht_das_speichern_nicht(self):
        t = self.neu("Mikro Mona")
        for kaputt in ("text", [1, 2], {"vitamin_c": "x"}, None, 5):
            self.assertEqual(self.api("POST", "/api/eintrag", {"name": "Test", "kcal": 1, "mikro": kaputt}, t)[0], 200, kaputt)


class TestDatenbankNachruestung(unittest.TestCase):
    def test_alte_datenbank_bekommt_die_spalte_mikro(self):
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE nutzer (id INTEGER PRIMARY KEY, name TEXT)")
        c.execute("CREATE TABLE eintrag (id INTEGER PRIMARY KEY, nutzer INTEGER, datum TEXT, mahlzeit TEXT, name TEXT, menge TEXT DEFAULT '', "
                  "kcal REAL, eiweiss REAL DEFAULT 0, kh REAL DEFAULT 0, fett REAL DEFAULT 0, quelle TEXT DEFAULT 'hand', erstellt INTEGER)")
        c.execute("INSERT INTO eintrag(nutzer, datum, mahlzeit, name, kcal, erstellt) VALUES (1,'2026-01-01','mittag','Altes Essen',100,0)")
        db._einrichten(c)
        spalten = {r["name"] for r in c.execute("PRAGMA table_info(eintrag)")}
        self.assertIn("mikro", spalten)
        self.assertEqual(c.execute("SELECT mikro FROM eintrag").fetchone()[0], "{}")        # alte Zeilen: leeres Mikro
        self.assertEqual(mikro.laden(c.execute("SELECT mikro FROM eintrag").fetchone()[0]), {})


if __name__ == "__main__":
    unittest.main()
