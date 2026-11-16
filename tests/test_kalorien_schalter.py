"""Registrierung per Schalter-Datei: wirkt sofort, schlaegt die .env, Telegram-Befehl."""
import os
import sys
import tempfile
import threading
import unittest
import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tests.test_kalorien import Basis  # noqa: E402  (setzt Test-Datenbank und KALORIEN_ADMINS=chef)
_TMP = tempfile.mkdtemp()
os.environ["KALORIEN_DB"] = str(Path(_TMP) / "k.db")
from kalorien import schalter, server  # noqa: E402
import kalorien_klaus as K  # noqa: E402


class TestSchalter(unittest.TestCase):
    def setUp(self):
        self.datei = Path(tempfile.mkdtemp()) / "reg.txt"
        p = mock.patch.dict(os.environ, {"KALORIEN_SCHALTER": str(self.datei)})
        p.start()
        self.addCleanup(p.stop)

    def test_ohne_datei_gilt_env(self):
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "0"}):
            self.assertFalse(schalter.offen())
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "1"}):
            self.assertTrue(schalter.offen())
        with mock.patch.dict(os.environ):
            os.environ.pop("KALORIEN_OFFEN", None)
            self.assertTrue(schalter.offen())   # Standard: offen

    def test_datei_schlaegt_env_in_beide_richtungen(self):
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "0"}):
            schalter.setzen(True)
            self.assertTrue(schalter.offen())
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "1"}):
            schalter.setzen(False)
            self.assertFalse(schalter.offen())

    def test_kaputte_datei_faellt_auf_env_zurueck(self):
        self.datei.write_text("irgendwas", encoding="utf-8")
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "0"}):
            self.assertFalse(schalter.offen())

    def test_telegram_befehl(self):
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "0"}):
            self.assertIn("GESCHLOSSEN", K.registrierung("/fit_registrierung"))
            self.assertIn("OFFEN", K.registrierung("/fit_registrierung an"))
            self.assertTrue(schalter.offen())
            self.assertIn("GESCHLOSSEN", K.registrierung("/fit_registrierung aus"))
            self.assertIn("Schreib:", K.registrierung("/fit_registrierung vielleicht"))
            self.assertFalse(schalter.offen())

    def test_befehl_ist_angemeldet(self):
        class TG:
            befehle, geheime_befehle = {}, set()
        tg = TG()
        K.befehle_einrichten(tg)
        self.assertIn("/fit_registrierung", tg.befehle)

    def test_registrierung_wirkt_sofort_ueber_http(self):
        srv = server.starten(port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/registrieren"

        def versuch(name):
            a = urllib.request.Request(url, data=json.dumps({"name": name, "passwort": "geheim1234"}).encode())
            try:
                with urllib.request.urlopen(a) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        with mock.patch.dict(os.environ, {"KALORIEN_OFFEN": "0"}):
            self.assertEqual(versuch("Zu Zora"), 403)
            schalter.setzen(True)                 # ohne Neustart
            self.assertEqual(versuch("Offen Otto"), 200)
            schalter.setzen(False)
            server._versuche.clear()
            self.assertEqual(versuch("Wieder Zu"), 403)


if __name__ == "__main__":
    unittest.main()


class TestCodeWaechter(unittest.TestCase):
    def test_nur_neu_starten_wenn_neuer_code_und_stabil(self):
        f = server.neustart_faellig
        self.assertEqual(f(100.0, 100.0, None), (False, None))        # nichts geaendert
        self.assertEqual(f(100.0, 200.0, None), (False, 200.0))       # erste Beobachtung: Update koennte noch kopieren
        self.assertEqual(f(100.0, 200.0, 200.0), (True, 200.0))       # beim zweiten Blick unveraendert -> neu starten
        self.assertEqual(f(100.0, 250.0, 200.0), (False, 250.0))      # wurde zwischendurch wieder geaendert -> weiter warten

    def test_code_stand_ist_eine_zahl(self):
        self.assertGreater(server.code_stand(), 0)


class TestProFuerAlle(Basis):
    def setUp(self):
        super().setUp()
        self.datei = Path(tempfile.mkdtemp()) / "pro.txt"
        p = mock.patch.dict(os.environ, {"KALORIEN_SCHALTER_PRO": str(self.datei)})
        p.start()
        self.addCleanup(p.stop)

    def test_standard_aus_env_und_datei(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("KALORIEN_PRO_FUER_ALLE", None)
            self.assertFalse(schalter.pro_fuer_alle())
        with mock.patch.dict(os.environ, {"KALORIEN_PRO_FUER_ALLE": "1"}):
            self.assertTrue(schalter.pro_fuer_alle())
            schalter.pro_fuer_alle_setzen(False)       # Datei schlaegt die .env
            self.assertFalse(schalter.pro_fuer_alle())
        schalter.pro_fuer_alle_setzen(True)
        self.assertTrue(schalter.pro_fuer_alle())

    def test_nutzer_wird_sofort_pro_und_wieder_nicht(self):
        t = self.neu("Alle-Pro Anton")
        plan = self.api("GET", "/api/ich", token=t)[1]["plan"]
        self.assertFalse(plan["pro"])
        self.assertFalse(plan["alle"])
        schalter.pro_fuer_alle_setzen(True)                                   # ohne Neustart
        plan = self.api("GET", "/api/ich", token=t)[1]["plan"]
        self.assertTrue(plan["pro"])
        self.assertTrue(plan["alle"])                                          # Pro nur wegen der Aktion
        self.assertGreater(plan["grenzen"]["ki"], 8)                           # Pro-Grenzen statt Frei-Grenzen
        schalter.pro_fuer_alle_setzen(False)
        self.assertFalse(self.api("GET", "/api/ich", token=t)[1]["plan"]["pro"])

    def test_admin_und_codeinhaber_bleiben_unabhaengig_vom_schalter(self):
        boss = self.neu("Chef") if self.api("POST", "/api/anmelden", {"name": "Chef", "passwort": "geheim1234"})[0] != 200 else \
            self.api("POST", "/api/anmelden", {"name": "Chef", "passwort": "geheim1234"})[1]["token"]
        schalter.pro_fuer_alle_setzen(False)
        plan = self.api("GET", "/api/ich", token=boss)[1]["plan"]
        self.assertTrue(plan["pro"] and plan["admin"])
        schalter.pro_fuer_alle_setzen(True)
        plan = self.api("GET", "/api/ich", token=boss)[1]["plan"]
        self.assertFalse(plan["alle"])                                         # Admin ist schon Pro, "alle" betrifft ihn nicht

    def test_telegram_befehl(self):
        import kalorien_klaus as K
        self.assertIn("aus", K.pro_alle("/fit_pro_alle"))
        self.assertIn("ALLE", K.pro_alle("/fit_pro_alle an"))
        self.assertTrue(schalter.pro_fuer_alle())
        self.assertIn("🔴", K.pro_alle("/fit_pro_alle aus"))
        self.assertFalse(schalter.pro_fuer_alle())
        self.assertIn("Schreib:", K.pro_alle("/fit_pro_alle vielleicht"))
