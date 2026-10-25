import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('KLAUS_LINK_TOKEN', 'x')
import server_gehirn   # noqa: F401  (PySide6-Attrappe)
import voice


class WhisperLadenTests(unittest.TestCase):
    def test_kaputter_download_wird_neu_geladen(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / 'models--Systran--faster-whisper-small' / 'snapshots' / 'abc'
            snap.mkdir(parents=True)
            versuche = []

            def modell(name, **_):
                versuche.append(name)
                if len(versuche) == 1:
                    raise RuntimeError(f"Unable to open file 'model.bin' in model '{snap}'")
                return 'OK'
            self.assertEqual(voice._whisper_laden(modell, 'small', device='cpu'), 'OK')
            self.assertEqual(len(versuche), 2)
            self.assertFalse((Path(tmp) / 'models--Systran--faster-whisper-small').exists())

    def test_anderer_fehler_bleibt(self):
        def modell(name, **_):
            raise RuntimeError('kein Speicher')
        with self.assertRaises(RuntimeError):
            voice._whisper_laden(modell, 'small')


if __name__ == '__main__':
    unittest.main()
