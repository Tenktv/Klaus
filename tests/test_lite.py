import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('KLAUS_LINK_TOKEN', 'x')
import server_gehirn  # noqa: F401  (PySide6-Attrappe fuer gemini_live/assistent)
import gemini_live
import identitaet
import klaus_einstellungen as E

SRC = Path(__file__).resolve().parents[1] / 'src'


class LiteTests(unittest.TestCase):
    def test_werkzeuge_gefiltert(self):
        voll = {w['name'] for w in gemini_live.werkzeuge()}
        with patch.object(identitaet, 'LITE', True):
            lite = {w['name'] for w in gemini_live.werkzeuge()}
        self.assertEqual(voll, {w['name'] for w in gemini_live.WERKZEUGE})
        self.assertTrue(gemini_live.LITE_WEG <= voll)
        self.assertFalse(lite & gemini_live.LITE_WEG)
        for nötig in ('oeffne', 'kalender_lesen', 'termin_eintragen', 'einstellungen', 'verbindungen', 'posten', 'chat_fenster', 'stimme', 'merken'):
            self.assertIn(nötig, lite)
        self.assertLess(len(lite), len(voll))

    def test_lite_flag_aus_env(self):
        for wert, erwartet in (('1', True), ('0', False), ('', False), ('ja', False)):
            with patch.dict(os.environ, {'KLAUS_LITE': wert}):
                import importlib
                importlib.reload(identitaet)
                self.assertEqual(identitaet.LITE, erwartet, wert)
        importlib.reload(identitaet)

    def test_einstellung_lite_und_modell(self):
        self.assertEqual(E.normalisieren('KLAUS_LITE', 'an'), '1')
        self.assertEqual(E.normalisieren('KLAUS_LITE', 'Ja'), '1')
        self.assertEqual(E.normalisieren('KLAUS_LITE', 'aus'), '0')
        with self.assertRaises(ValueError):
            E.normalisieren('KLAUS_LITE', 'vielleicht')
        self.assertEqual(E.normalisieren('WHISPER_MODEL', ' Base '), 'base')
        with self.assertRaises(ValueError):
            E.normalisieren('WHISPER_MODEL', 'riesig')

    def test_zurueck_zur_vollen_oberflaeche_nur_wenn_sie_da_ist(self):
        with patch.dict(os.environ, {'KLAUS_LITE': '1'}), patch.object(E, '_web_oberflaeche_da', lambda: False):
            with self.assertRaises(ValueError) as e:
                E.normalisieren('KLAUS_LITE', 'aus')
            self.assertIn('Setup.exe', str(e.exception))
        with patch.dict(os.environ, {'KLAUS_LITE': '1'}), patch.object(E, '_web_oberflaeche_da', lambda: True):
            self.assertEqual(E.normalisieren('KLAUS_LITE', 'aus'), '0')

    def test_klaus_app_startet_lite_bevor_die_web_oberflaeche_geladen_wird(self):
        quelle = (SRC / 'klaus_app.py').read_text(encoding='utf-8')
        wache, fenster = quelle.index('klaus_lite.main()'), quelle.index('from fenster import')
        self.assertLess(wache, fenster)
        self.assertLess(quelle.index('if _identitaet.LITE'), fenster)

    def test_lite_ohne_web_engine_und_installer(self):
        lite = (SRC / 'klaus_lite.py').read_text(encoding='utf-8')
        self.assertFalse(re.search(r'^\s*(import|from)\s+(fenster|stream|stream_overlay|spielmodus)\b|QtWebEngine', lite, re.M))
        ps = (SRC.parent / 'installer' / 'einrichten.ps1').read_text(encoding='utf-8')
        self.assertIn('PySide6-Essentials', ps)
        self.assertIn("if (-not $Lite) { & $venvPy -m playwright install chromium }", ps)
        iss = (SRC.parent / 'installer' / 'klaus.iss').read_text(encoding='utf-8')
        self.assertIn("'KLAUS_LITE=1'", iss)
        self.assertIn('{code:LiteSchalter}', iss)


SKRIPT = """
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, %r)
from PySide6.QtWidgets import QApplication
app = QApplication([])
import identitaet, klaus_lite
gesendet = []
w = klaus_lite.ChatFenster(gesendet.append)
w.zeile.setText('  Wie spät ist es?  ')
w.knopf.click()
assert gesendet == ['Wie spät ist es?'], gesendet
assert w.zeile.text() == ''
w.neu.emit('klaus', 'Kurz nach drei.')
w.status.emit('hört zu …')
app.processEvents()
assert f'{identitaet.NAME}: Kurz nach drei.' in w.verlauf.toPlainText(), w.verlauf.toPlainText()
assert w.statuszeile.text() == 'hört zu …'
for modul in ('fenster', 'stream', 'stream_overlay', 'spielmodus', 'PySide6.QtWebEngineWidgets'):
    assert modul not in sys.modules, modul
print('LITE_OK')
"""


def _echtes_qt() -> bool:
    import subprocess
    return subprocess.run([sys.executable, '-c', 'import PySide6.QtWidgets'], capture_output=True).returncode == 0


@unittest.skipUnless(_echtes_qt(), 'braucht echtes PySide6')
class LiteFenster(unittest.TestCase):
    def test_chat_fenster_in_eigenem_prozess(self):   # eigener Prozess: server_gehirn ersetzt PySide6 hier durch eine Attrappe
        import subprocess
        r = subprocess.run([sys.executable, '-c', SKRIPT % str(SRC)], capture_output=True, text=True, timeout=60)
        self.assertIn('LITE_OK', r.stdout, r.stdout + r.stderr[-800:])


if __name__ == '__main__':
    unittest.main()
