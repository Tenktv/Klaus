import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import freigabe
import pc_update as pu

TEST_OHNE_APP = ("import glob, py_compile; [py_compile.compile(f, doraise=True) for f in glob.glob('src/*.py')]; print('TEST_OK')")


def git(ordner, *args):
    subprocess.run(['git', *args], cwd=ordner, check=True, capture_output=True,
                   env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'})


class PcUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.quelle, self.pc = t / 'quelle', t / 'pc'
        self.quelle.mkdir()
        git(self.quelle, 'init', '-q', '-b', 'main')
        (self.quelle / 'src').mkdir()
        (self.quelle / 'src' / 'a.py').write_text('x = 1\n')
        git(self.quelle, 'add', '.')
        git(self.quelle, 'commit', '-q', '-m', 'start')
        git(t, 'clone', '-q', str(self.quelle), str(self.pc))
        for name, wert in (('BASE_DIR', self.pc), ('MARKER', self.pc / 'data' / 'marker.json'), ('TEST', TEST_OHNE_APP)):
            p = patch.object(pu, name, wert)
            p.start()
            self.addCleanup(p.stop)
        self.neustarts = []
        p = patch.object(pu, 'neustart', lambda: self.neustarts.append(1))
        p.start()
        self.addCleanup(p.stop)
        self.gesendet = []
        self.assistent = SimpleNamespace(letzte_aktivitaet=0.0, gemini=None, protokoll=None, log=lambda t: None,
                                         fern=SimpleNamespace(senden=self.gesendet.append))
        pu._zuletzt_gemeldet['text'] = ''

    def commit(self, inhalt, msg):
        (self.quelle / 'src' / 'a.py').write_text(inhalt)
        git(self.quelle, 'commit', '-q', '-am', msg)

    def kopf(self):
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.pc, capture_output=True, text=True).stdout

    def test_nichts_neu(self):
        self.assertFalse(pu.schritt(self.assistent))
        self.assertEqual(self.neustarts, [])

    def test_update_wird_eingespielt_und_neu_gestartet(self):
        self.commit('x = 2\n', 'Neue Funktion')
        self.assertTrue(pu.schritt(self.assistent))
        self.assertEqual((self.pc / 'src' / 'a.py').read_text(), 'x = 2\n')
        self.assertEqual(self.neustarts, [1])
        meldung = pu.nach_neustart()
        self.assertIn('Neue Funktion', meldung)
        self.assertIsNone(pu.nach_neustart())

    def test_kaputtes_update_wird_zurueckgerollt(self):
        alt = self.kopf()
        self.commit('def kaputt(:\n', 'Kaputt')
        self.assertFalse(pu.schritt(self.assistent))
        self.assertEqual(self.kopf(), alt)
        self.assertEqual((self.pc / 'src' / 'a.py').read_text(), 'x = 1\n')
        self.assertIn('fehlgeschlagen', self.gesendet[0])
        self.assertEqual(self.neustarts, [])

    def test_lokale_aenderungen_werden_nicht_ueberschrieben_und_nur_einmal_gemeldet(self):
        (self.pc / 'src' / 'a.py').write_text('x = 99\n')
        self.commit('x = 2\n', 'Neu')
        pu.schritt(self.assistent)
        pu.schritt(self.assistent)
        self.assertEqual((self.pc / 'src' / 'a.py').read_text(), 'x = 99\n')
        self.assertEqual(len(self.gesendet), 1)
        self.assertIn('lokale', self.gesendet[0])

    def test_wartet_wenn_klaus_beschaeftigt(self):
        self.commit('x = 2\n', 'Neu')
        self.assistent.letzte_aktivitaet = time.time()
        self.assertFalse(pu.schritt(self.assistent))
        self.assistent.letzte_aktivitaet = 0.0
        freigabe._offen['x'] = SimpleNamespace(erstellt=time.time())
        try:
            self.assertFalse(pu.schritt(self.assistent))
        finally:
            freigabe._offen.pop('x')
        self.assertTrue(pu.schritt(self.assistent))

    def test_abschaltbar(self):
        self.commit('x = 2\n', 'Neu')
        with patch.dict(os.environ, {'KLAUS_AUTO_UPDATE': '0'}):
            self.assertFalse(pu.schritt(self.assistent))


if __name__ == '__main__':
    unittest.main()
