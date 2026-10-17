import io
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import server_claude as sc


class ServerClaudeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        heim = Path(self.tmp.name)
        for name, wert in (('HEIM', heim), ('ARBEIT', heim / 'arbeit'), ('PROJEKTE', heim / 'projekte')):
            p = patch.object(sc, name, wert)
            p.start()
            self.addCleanup(p.stop)

    def test_status_erklaert_was_fehlt(self):
        with patch.object(sc, '_programm', lambda: None):
            self.assertIn('nicht installiert', sc.status())
        with patch.object(sc, '_programm', lambda: '/x/claude'), patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': '', 'ANTHROPIC_API_KEY': ''}):
            self.assertIn('/claude_token', sc.status())
        with patch.object(sc, '_programm', lambda: '/x/claude'), patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': 'sk-ant-oat01-abc'}):
            self.assertIn('bereit', sc.status())

    def test_token_nur_gueltiges_format(self):
        gespeichert = {}
        self.assertIn('So:', sc.token_setzen('/claude_token', gespeichert.__setitem__))
        self.assertIn('nichts gespeichert', sc.token_setzen('/claude_token sk-ant-api03-xyz', gespeichert.__setitem__))
        self.assertEqual(gespeichert, {})
        token = 'sk-ant-oat01-' + 'a' * 40
        with patch.object(sc, '_programm', lambda: '/x/claude'), patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': token}):
            self.assertIn('gespeichert', sc.token_setzen(f'/claude_token {token}', gespeichert.__setitem__))
        self.assertEqual(gespeichert, {'CLAUDE_CODE_OAUTH_TOKEN': token})

    def test_frage_ohne_geheimnisse_in_der_umgebung(self):
        aufrufe = []

        def run(befehl, **kw):
            aufrufe.append((befehl, kw))
            return SimpleNamespace(stdout=json.dumps({'result': '**Antwort** 42', 'is_error': False}), stderr='')
        with patch.object(sc, '_programm', lambda: '/x/claude'), patch.object(sc.subprocess, 'run', run), \
                patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': 'sk-ant-oat01-x', 'ALPACA_SECRET_KEY': 'geheim', 'TELEGRAM_TOKEN': 't'}):
            self.assertEqual(sc.frage('Was ist 6*7?'), 'Antwort 42')
        befehl, kw = aufrufe[0]
        self.assertIn('-p', befehl)
        self.assertNotIn('Bash', befehl)
        self.assertNotIn('ALPACA_SECRET_KEY', kw['env'])
        self.assertNotIn('TELEGRAM_TOKEN', kw['env'])
        self.assertIn('CLAUDE_CODE_OAUTH_TOKEN', kw['env'])

    def test_frage_nicht_eingerichtet_klare_meldung(self):
        with patch.object(sc, '_programm', lambda: None):
            self.assertIn('nicht installiert', sc.frage('hallo'))

    def test_bauen_schickt_zip(self):
        fertig, ende = [], threading.Event()

        def run(befehl, cwd, **kw):
            (Path(cwd) / 'index.html').write_text('<h1>Hallo</h1>')
            self.assertIn('acceptEdits', befehl)
            self.assertNotIn('Bash', befehl)
            return SimpleNamespace(stdout=json.dumps({'result': 'Website gebaut.', 'is_error': False}), stderr='')

        def melden(text, daten, name):
            fertig.append((text, daten, name))
            ende.set()
        with patch.object(sc, '_programm', lambda: '/x/claude'), patch.object(sc.subprocess, 'run', run), \
                patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': 'sk-ant-oat01-x'}):
            self.assertIn('Cloud', sc.bauen('Website für Bäckerei Müller', 'Bäckerei Müller', melden))
            self.assertTrue(ende.wait(5))
        text, daten, name = fertig[0]
        self.assertIn('fertig', text)
        self.assertEqual(name, 'baeckerei-mueller.zip')
        self.assertEqual(zipfile.ZipFile(io.BytesIO(daten)).namelist(), ['index.html'])


if __name__ == '__main__':
    unittest.main()
