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
