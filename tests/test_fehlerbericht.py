import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import fehlerbericht as FB
import fehlerberichte as FS


class FehlerberichtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.TemporaryDirectory()
        cls.p = patch.object(FS, 'CODES', Path(cls.ordner.name) / 'melde_codes.json')
        cls.p.start()
        cls.nachrichten, cls.dateien = [], []
        cls.port = 17720 + os.getpid() % 1000
        with patch.object(FS, 'PORT', cls.port):
            cls.server = FS.starten(cls.nachrichten.append, lambda inhalt, name, text: cls.dateien.append((inhalt, name)))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.p.stop()
        cls.ordner.cleanup()

    def setUp(self):
        FS._zaehler.update(tag='', gesamt=0, codes={})
        self.log = Path(self.ordner.name) / 'klaus.log'
        self.log.write_text('Start\nTraceback (most recent call last):\n  File "C:\\\\x\\\\voice.py", line 142, in __init__\n'
                            'RuntimeError: Unable to open file model.bin\nGeheim: AIzaSyA1234567890123456789012345678901234\n',
                            encoding='utf-8')
        self.env = patch.dict(os.environ, {'KLAUS_BERICHT_URL': f'http://127.0.0.1:{self.port}/bericht',
                                           'GEMINI_API_KEY': 'mein-gemini-geheimnis-123'})
        self.env.start()
        self.lp = patch.object(FB, 'LOG', self.log)
        self.lp.start()

    def tearDown(self):
        self.env.stop()
        self.lp.stop()

    def warte(self, n):
        ende = time.time() + 3
        while len(self.dateien) < n and time.time() < ende:
            time.sleep(0.02)

    def test_bericht_kommt_bei_nikola_an_ohne_geheimnisse(self):
        code = FS.code_anlegen('Tim')
        with patch.dict(os.environ, {'KLAUS_MELDE_CODE': code}):
            self.assertIn('an Nikola geschickt', FB.senden('Klaus startet nicht'))
        self.warte(1)
        self.assertIn('Fehlerbericht von Tim', self.nachrichten[-1])
        self.assertIn('Unable to open file model.bin', self.nachrichten[-1])   # letzter Fehler in der Kurzfassung
        inhalt = self.dateien[-1][0].decode()
        for geheim in ('AIzaSyA123456', 'mein-gemini-geheimnis-123', code):
            self.assertNotIn(geheim, inhalt + self.nachrichten[-1])
        self.assertIn('Gemini: ja', inhalt)

    def test_unbekannter_code_und_ohne_code(self):
        vorher = len(self.nachrichten)
        with patch.dict(os.environ, {'KLAUS_MELDE_CODE': 'km_falschfalschfalschfalsch'}):
            self.assertIn('Melde-Code stimmt nicht', FB.senden('x'))
        with patch.dict(os.environ, {'KLAUS_MELDE_CODE': ''}):
            self.assertIn('fehlt der Melde-Code', FB.senden('x'))
        time.sleep(0.2)
        self.assertEqual(len(self.nachrichten), vorher)

    def test_grenze_pro_minute_und_sperren(self):
        code = FS.code_anlegen('Anna')
        with patch.dict(os.environ, {'KLAUS_MELDE_CODE': code}):
            self.assertIn('geschickt', FB.senden('eins'))
            self.assertIn('429', FB.senden('zwei'))
        self.assertTrue(FS.code_weg('Anna'))
        self.assertEqual(FS.pruefen(code)[0], 403)

    def test_neuer_code_macht_alten_ungueltig(self):
        alt = FS.code_anlegen('Lea')
        neu = FS.code_anlegen('Lea')
        self.assertEqual(FS.pruefen(alt)[0], 403)
        self.assertEqual(FS.pruefen(neu)[0], 200)
        self.assertNotIn(neu, FS.CODES.read_text())   # nur der Hash wird gespeichert

    def test_zu_gross(self):
        import requests
        code = FS.code_anlegen('Max')
        r = requests.post(f'http://127.0.0.1:{self.port}/bericht', data=b'x' * (FS.MAX_BYTES + 1),
                          headers={'X-Melde-Code': code}, timeout=5)
        self.assertEqual(r.status_code, 413)

    def test_automatisch_nur_einmal(self):
        gesendet = []
        with patch.dict(os.environ, {'KLAUS_MELDE_CODE': 'km_x' * 6}), patch.object(FB, 'senden', gesendet.append), \
                patch('time.sleep'):
            FB._z.update(zuletzt=0.0, gesendet=set())
            FB.automatisch('Fehler im Gespräch', 'Traceback A')
            FB.automatisch('Fehler im Gespräch', 'Traceback A')
            time.sleep(0)
        ende = time.time() + 2
        while not gesendet and time.time() < ende:
            pass
        self.assertEqual(gesendet, ['Fehler im Gespräch'])

    def test_telegram_befehle(self):
        class TG:
            befehle = {}
        FS.befehle_einrichten(TG)
        antwort = TG.befehle['/melde_code']('/melde_code Paul')
        self.assertIn('KLAUS_MELDE_CODE=km_', antwort)
        self.assertIn('Paul', TG.befehle['/melde_codes']('/melde_codes'))
        self.assertIn('gesperrt', TG.befehle['/melde_code_weg']('/melde_code_weg Paul'))


if __name__ == '__main__':
    unittest.main()
