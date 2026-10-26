import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('KLAUS_LINK_TOKEN', 'x')
import server_gehirn   # noqa: F401  (PySide6-Attrappe)
import assistent as A
import klaus_einstellungen as E
import verbindungen as V

NAMEN = ['KLAUS_NAME', 'KLAUS_NUTZER', 'GEMINI_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY', 'ERSATZ_KI_URL', 'ERSATZ_KI_KEY',
         'ERSATZ_KI_MODELLE', 'FISH_API_KEY', 'KLAUS_MIC', 'KLAUS_UPDATE_TOKEN', 'KLAUS_MELDE_CODE']


class Antwort:
    def __init__(self, status, daten=None):
        self.status_code, self._d, self.text = status, daten or {}, ''

    def json(self):
        return self._d


class EinstellungenTests(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {n: '' for n in NAMEN})
        self.env.start()
        self.datei = patch.object(V, 'ENV_DATEI', Path(self.ordner.name) / '.env')
        self.datei.start()

    def tearDown(self):
        self.datei.stop()
        self.env.stop()
        self.ordner.cleanup()

    def test_name_pruefen(self):
        self.assertEqual(E.normalisieren('KLAUS_NAME', ' Lumine '), 'Lumine')
        for falsch in ('Lu mine', 'L', 'Klaus123'):
            with self.assertRaises(ValueError, msg=falsch):
                E.normalisieren('KLAUS_NAME', falsch)
        self.assertEqual(E.normalisieren('ERSATZ_KI_URL', 'http://localhost:1234/v1/'), 'http://localhost:1234/v1')
        with self.assertRaises(ValueError):
            E.normalisieren('GEMINI_API_KEY', 'AIza mit leerzeichen')

    def test_speichern_und_zustand(self):
        self.assertEqual(E.zustand('gemini'), 'nein')
        E.speichern('gemini', {'GEMINI_API_KEY': 'AIzaTest123'})
        self.assertEqual(E.zustand('gemini'), 'ja')
        self.assertIn('GEMINI_API_KEY=AIzaTest123', V.ENV_DATEI.read_text())
        E.speichern('gemini', {'GEMINI_API_KEY': ''})   # leer = behalten
        self.assertEqual(os.environ['GEMINI_API_KEY'], 'AIzaTest123')
        E.trennen('gemini')
        self.assertEqual(E.zustand('gemini'), 'nein')

    def test_mikrofon_leer_heisst_standard(self):
        E.speichern('mikrofon', {'KLAUS_MIC': 'Yeti'})
        self.assertEqual(os.environ['KLAUS_MIC'], 'Yeti')
        E.speichern('mikrofon', {'KLAUS_MIC': ''})
        self.assertEqual(os.environ['KLAUS_MIC'], '')

    def test_gemini_testen(self):
        os.environ['GEMINI_API_KEY'] = 'AIzaTest123'
        with patch('requests.get', return_value=Antwort(200)):
            self.assertIn('✓', E.testen('gemini'))
        with patch('requests.get', return_value=Antwort(400, {'error': {'message': 'API key not valid'}})):
            self.assertIn('API key not valid', E.testen('gemini'))

    def test_ersatz_testen(self):
        os.environ['GROQ_API_KEY'] = 'gsk_test'
        with patch('requests.get', return_value=Antwort(401)):
            self.assertIn('abgelehnt', E.testen('ersatz'))

    def test_finde(self):
        self.assertEqual(E.finde('mikrofon'), 'mikrofon')
        self.assertEqual(E.finde('fish'), 'fish')
        self.assertEqual(E.finde('quatsch'), '')


class SpracheTests(unittest.TestCase):
    def test_einstellungen_erkannt(self):
        for t in ('öffne deine Einstellungen', 'zeig mir die Klaus-Einstellungen', 'ich will meine Schlüssel eintragen',
                  'ändere deinen Namen', 'Mikrofon wechseln'):
            self.assertTrue(A.EINSTELLUNGEN.search(t), t)
        for t in ('öffne die Einstellungen', 'öffne Windows Einstellungen', 'ich hab ein neues Mikro gekauft'):
            self.assertFalse(A.EINSTELLUNGEN.search(t), t)   # Windows-Einstellungen bleiben bei apps.py

    def test_werkzeug_da(self):
        import gemini_live
        self.assertIn('einstellungen', [w['name'] for w in gemini_live.WERKZEUGE])


if __name__ == '__main__':
    unittest.main()
