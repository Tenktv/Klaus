"""Klaus <-> Kalorien-App: Telegram-Befehle gegen eine echte (lokale) App-Instanz, KI gefaelscht."""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ["KALORIEN_DB"] = str(Path(tempfile.mkdtemp()) / "k.db")
from kalorien import ki, server  # noqa: E402
import kalorien_klaus as K  # noqa: E402

FAKE = {"gerichte": [{"name": "Rührei", "menge": "2 Eier", "kcal": 180, "eiweiss": 12, "kh": 1, "fett": 14},
                     {"name": "Toast", "menge": "1 Scheibe", "kcal": 80, "eiweiss": 3, "kh": 15, "fett": 1}], "hinweis": "grob"}


class TestKlausBruecke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.starten(port=0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.env = {"KALORIEN_URL": f"http://127.0.0.1:{cls.srv.server_address[1]}"}
        with mock.patch.dict(os.environ, cls.env):
            import json
            import urllib.request
            def post(pfad, d, t=None):
                a = urllib.request.Request(cls.env["KALORIEN_URL"] + "/api/" + pfad, data=json.dumps(d).encode(),
                                           headers={"Authorization": f"Bearer {t}"} if t else {})
                return json.loads(urllib.request.urlopen(a).read())
            sitzung = post("registrieren", {"name": "Klaus Kunde", "passwort": "geheim1234"})["token"]
            cls.env["KALORIEN_TOKEN"] = post("zugang", {"name": "Klaus"}, sitzung)["token"]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        p = mock.patch.dict(os.environ, self.env)
        p.start()
        self.addCleanup(p.stop)
        K._letzte.clear()

    def test_ohne_schluessel_klare_anleitung(self):
        with mock.patch.dict(os.environ, {"KALORIEN_TOKEN": ""}):
            self.assertIn("noch nicht verbunden", K.kalorien())
            self.assertFalse(K.ist_essensfoto("Essen"))

    def test_essen_tragen_ein_und_zeigen_rest(self):
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "_aufrufen", return_value=FAKE):
            antwort = K.essen("/essen 2 Eier mit Toast")
        self.assertIn("Rührei", antwort)
        self.assertIn("260 kcal", antwort)
        heute = K.kalorien()
        self.assertIn("260 von 2000", heute)
        self.assertIn("Toast", heute)

    def test_essen_weg_nimmt_zurueck(self):
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "_aufrufen", return_value=FAKE):
            K.essen("/essen irgendwas")
        before = K.kalorien()
        self.assertIn("zurückgenommen", K.essen_weg())
        self.assertNotEqual(before, K.kalorien())
        self.assertIn("nichts Frisches", K.essen_weg())

    def test_foto_nur_mit_essen_beschriftung(self):
        self.assertTrue(K.ist_essensfoto("Essen: mit Hafermilch"))
        self.assertTrue(K.ist_essensfoto("kalorien"))
        self.assertFalse(K.ist_essensfoto("Arbeit"))
        self.assertFalse(K.ist_essensfoto("Essensplan Montag"))   # Wortgrenze: das ist ein Plan, kein Essensfoto
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "aus_bild", return_value=FAKE) as m:
            out = K.foto(b"\xff\xd8" + b"0" * 3000, "Essen mit Hafermilch")
        self.assertIn("Eingetragen", out)
        self.assertEqual(m.call_args[0][2], "mit Hafermilch")

    def test_falscher_schluessel_und_app_aus(self):
        with mock.patch.dict(os.environ, {"KALORIEN_TOKEN": "kt_falsch"}):
            self.assertIn("Schlüssel", K.kalorien())
        with mock.patch.dict(os.environ, {"KALORIEN_URL": "http://127.0.0.1:9"}):
            self.assertIn("nicht erreichbar", K.kalorien())

    def test_ki_fehler_wird_freundlich(self):
        with mock.patch.object(ki, "schluessel", return_value=""):
            self.assertIn("nicht eingerichtet", K.essen("/essen Brot"))


if __name__ == "__main__":
    unittest.main()
