"""Lead-Suche auf dem Server (ohne PC): Parameter, Ergebnis-Nachricht, leere Treffer, Fehler."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import leads_server  # noqa: E402
import osm_leads  # noqa: E402


class TestLeadsServer(unittest.TestCase):
    def test_parameter(self):
        self.assertEqual(leads_server.parameter({"branchen": "Schreiner, Maler und Friseure"}), (["Schreiner", "Maler", "Friseure"], "Göppingen", 12.0))
        self.assertEqual(leads_server.parameter({"branchen": "Bäcker", "ort": "Ulm", "radius_km": 500})[1:], ("Ulm", 40.0))
        self.assertEqual(leads_server.parameter({"branchen": "x", "radius_km": "kaputt"})[2], 12.0)

    def test_ohne_branche_wird_nachgefragt(self):
        self.assertIn("Welche Branchen", leads_server.starten({}, lambda t: None, lambda *a: None))

    def test_ergebnis_kommt_als_nachricht_und_csv(self):
        leads = [{"name": f"Firma {i}", "adresse": f"Weg {i}, 73033 Göppingen", "telefon": "07161 1"} for i in range(30)]
        texte, dateien = [], []
        with mock.patch.object(osm_leads, "suche", return_value=leads), mock.patch.object(osm_leads, "websites_pruefen", side_effect=lambda l: l), \
                mock.patch.object(osm_leads, "speichern", return_value=30):
            leads_server.suchen(["Maler"], "Göppingen", 12.0, texte.append, lambda *a: dateien.append(a))
        self.assertIn("30 Betriebe ohne eigene Website", texte[0])
        self.assertIn("Firma 0", texte[0])
        self.assertIn("…", texte[0])                       # nur 25 in der Nachricht
        self.assertEqual(dateien[0][1], "leads_G_ppingen.csv")
        self.assertIn(b"Firma 29", dateien[0][0])           # alle in der CSV

    def test_keine_treffer_und_alle_mit_website(self):
        t = []
        with mock.patch.object(osm_leads, "suche", return_value=[]):
            leads_server.suchen(["Maler"], "Ulm", 5.0, t.append, None)
        self.assertIn("keine passenden Betriebe", t[0])
        t = []
        with mock.patch.object(osm_leads, "suche", return_value=[{"name": "A", "adresse": "x"}]), mock.patch.object(osm_leads, "websites_pruefen", return_value=[]), \
                mock.patch.object(osm_leads, "speichern", return_value=0):
            leads_server.suchen(["Maler"], "Ulm", 5.0, t.append, None)
        self.assertIn("alle haben schon eine Website", t[0])

    def test_fehler_wird_ehrlich_gemeldet(self):
        t = []
        with mock.patch.object(osm_leads, "suche", side_effect=RuntimeError("Overpass 504")):
            leads_server.suchen(["Maler"], "Ulm", 5.0, t.append, None)
        self.assertIn("nicht geklappt: Overpass 504", t[0])

    def test_server_leitet_die_werkzeug_nicht_mehr_an_den_pc(self):
        quelle = (Path(__file__).resolve().parent.parent / "src" / "server_gehirn.py").read_text(encoding="utf-8")
        self.assertIn('name == "leads_suchen"', quelle)
        self.assertIn("leads_server.starten", quelle)


if __name__ == "__main__":
    unittest.main()
