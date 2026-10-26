import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import stimmwahl as S


class StimmenKatalogTests(unittest.TestCase):
    def test_namen_eindeutig_und_vollstaendig(self):
        namen = [S._normal(s['name']) for s in S.EINGEBAUT]
        self.assertEqual(len(namen), len(set(namen)))
        for s in S.EINGEBAUT:
            self.assertIn(s['art'], ('gemini', 'edge', 'piper'))
            if s['art'] == 'piper':
                self.assertTrue(s['laden'].startswith('de_DE-') and s['id'].endswith(s['laden'] + '.onnx'), s)
        self.assertGreaterEqual(sum(s['art'] == 'edge' for s in S.EINGEBAUT), 25)

    def test_offline_stimme_wird_erst_geladen(self):
        with tempfile.TemporaryDirectory() as tmp:
            basis = Path(tmp)
            geladen = []

            def laden(s):
                geladen.append(s['laden'])
                (basis / s['id']).parent.mkdir(parents=True, exist_ok=True)
                (basis / s['id']).write_bytes(b'x')
            with patch.object(S, 'BASE_DIR', basis), patch.object(S, 'ORDNER', basis / 'data' / 'stimmen'), \
                    patch.object(S, 'DATEI', basis / 'data' / 'stimmen' / 'stimmen.json'), patch.object(S, 'piper_laden', laden):
                antwort = S.waehlen('Kerstin')
                self.assertIn('lade', antwort)
                ende = time.time() + 2
                while S._laden()['aktiv'] != 'Kerstin' and time.time() < ende:
                    time.sleep(0.01)
                self.assertEqual(geladen, ['de_DE-kerstin-low'])
                self.assertEqual(S._laden()['aktiv'], 'Kerstin')
                self.assertIn('Kerstin', S.waehlen('Kerstin'))   # schon da -> sofort umschalten
                self.assertEqual(len(geladen), 1)
                self.assertEqual([s for s in S.alle() if s['name'] == 'Kerstin'][0]['art'], 'piper')
                self.assertNotIn('Kerstin Low', [s['name'] for s in S.alle()])   # nicht doppelt

    def test_akzent_stimme_finden(self):
        self.assertEqual(S.finden('Andrew')['id'], 'en-US-AndrewMultilingualNeural')
        self.assertEqual(S.finden('opa')['tonhoehe'], '-22Hz')


if __name__ == '__main__':
    unittest.main()
