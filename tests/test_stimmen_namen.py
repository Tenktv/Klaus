import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import identitaet
import pc_update as pu
import stimmwahl as sw


class NamenTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(identitaet)

    def laden(self, **env):
        with patch.dict(os.environ, {'KLAUS_NAME': '', 'KLAUS_NUTZER': '', **env}), patch('dotenv.load_dotenv'):
            return importlib.reload(identitaet)

    def test_standard_bleibt_klaus_und_nikola(self):
        i = self.laden()
        self.assertEqual(i.anpassen('Klaus hilft Nikola Georgiev.'), 'Klaus hilft Nikola Georgiev.')
        self.assertTrue(re.fullmatch(i.weckwort_muster(), 'claus'))

    def test_eigener_name_und_weckwort(self):
        i = self.laden(KLAUS_NAME='Luna', KLAUS_NUTZER='Tim')
        self.assertEqual(i.anpassen("Du bist Klaus. KLAUS hilft Nikola. Klaus' Stimme."), "Du bist Luna. LUNA hilft Tim. Luna' Stimme.")
        self.assertTrue(re.fullmatch(i.weckwort_muster(), 'luna'))
        self.assertFalse(re.fullmatch(i.weckwort_muster(), 'klaus'))

    def test_fremde_persona_ohne_nikolas_daten(self):
        i = self.laden(KLAUS_NAME='Luna', KLAUS_NUTZER='Tim')
        p = i.anpassen_persona('Du bist Klaus von Nikola. Nikola betreibt Klesro Web in Goeppingen.\n\nWie du denkst: ehrlich.')
        self.assertNotIn('Klesro', p)
        self.assertIn('Luna', p)
        self.assertIn('Tim', p)
        self.assertIn('Wie du denkst', p)
        i = self.laden(KLAUS_NUTZER='Nikola')
        self.assertIn('Klesro', i.anpassen_persona('Nikola betreibt Klesro.\n\nRest'))


class StimmenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        o = Path(self.tmp.name)
        for name, wert in (('ORDNER', o), ('DATEI', o / 'stimmen.json'), ('EIGENE_PROBEN', o / 'eigene'), ('BASE_DIR', o)):
            p = patch.object(sw, name, wert)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'FISH_API_KEY': '', 'KLAUS_STIMME_ANBIETER': 'gemini', 'GEMINI_STIMME': 'Charon'})
        p.start()
        self.addCleanup(p.stop)

    def test_standard_und_wechsel(self):
        self.assertEqual(sw.aktiv()['name'], 'Charon')
        self.assertFalse(sw.extern_aktiv())
        self.assertIn('nächsten Gespräch', sw.waehlen('anime mädchen'))
        self.assertEqual(sw.aktiv()['name'], 'Anime-Mädchen')
        self.assertTrue(sw.extern_aktiv())
        self.assertEqual(sw.lokale_kennung(), 'edge:de-DE-SeraphinaMultilingualNeural@+38Hz@+12%')
        self.assertNotIn('nächsten', sw.waehlen('Sensei'))     # extern -> extern: sofort
        self.assertEqual(sw.gemini_stimme(), 'Charon')
        sw.waehlen('Puck')
        self.assertEqual(sw.gemini_stimme(), 'Puck')

    def test_unbekannt_und_fish_ohne_schluessel(self):
        with self.assertRaises(sw.StimmFehler):
            sw.waehlen('Gibtsnicht')
        with self.assertRaises(sw.StimmFehler):
            sw.fish_uebernehmen('Gojo', 'https://fish.audio/m/' + 'a' * 32)
        self.assertIn('kenne ich nicht', sw.befehl('/stimme Gibtsnicht'))

    def test_eigene_stimmen(self):
        sw.edge_hinzufuegen('Kitsune', 'Seraphina', '+30Hz', '+15%')
        with self.assertRaises(sw.StimmFehler):
            sw.edge_hinzufuegen('X', 'Seraphina', '30')        # falsches Format
        with self.assertRaises(sw.StimmFehler):
            sw.edge_hinzufuegen('Florian', 'Seraphina')        # Name schon eingebaut
        with patch.dict(os.environ, {'FISH_API_KEY': 'k'}):
            sw.fish_uebernehmen('Gojo', 'https://fish.audio/m/' + 'ab' * 16 + '/')
            self.assertIn('Gojo', sw.waehlen('gojo'))
        self.assertEqual(sw.aktiv()['art'], 'fish')
        self.assertEqual(sw.lokale_kennung(), 'fish:' + 'ab' * 16)
        self.assertIn('Kitsune', sw.liste_text())
        sw.loeschen('Gojo')
        self.assertEqual(sw.aktiv()['name'], 'Charon')       # geloeschte aktive Stimme -> Standard
        with self.assertRaises(sw.StimmFehler):
            sw.loeschen('Charon')

    def test_klonen_braucht_probe(self):
        with patch.dict(os.environ, {'FISH_API_KEY': 'k'}):
            with self.assertRaises(sw.StimmFehler) as f:
                sw.klonen('Meine Stimme')
            self.assertIn('Meine Stimme.mp3', str(f.exception))
            (sw.EIGENE_PROBEN / 'meine stimme.mp3').write_bytes(b'ID3')
            with patch.object(sw, '_fish_modell', lambda datei, titel, *a: 'c' * 32):
                sw.klonen('Meine Stimme')
        self.assertEqual(sw.finden('meine stimme')['id'], 'c' * 32)

    def test_pcm_24khz_aus_edge(self):
        sw.waehlen('Chibi')
        fake = SimpleNamespace(saetze=lambda k, t: iter([(np.zeros(48000, dtype=np.float32), 48000)]))
        with patch.dict(sys.modules, {'stimme': fake}):
            daten = b''.join(sw.pcm_strom('Hallo'))
        self.assertEqual(len(daten) // 2, 24000)            # 1 s bei 24 kHz, int16


class ReleaseUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        o = Path(self.tmp.name)
        (o / 'VERSION').write_text('1.0.0')
        for name, wert in (('BASE_DIR', o), ('MARKER', o / 'data' / 'm.json')):
            p = patch.object(pu, name, wert)
            p.start()
            self.addCleanup(p.stop)
        self.setup = b'MZ setup'
        self.hash = hashlib.sha256(self.setup).hexdigest()

    def api(self, tag='v1.1.0', body=None):
        d = {'tag_name': tag, 'body': body if body is not None else f'SHA256: {self.hash}',
             'assets': [{'name': 'Klaus-Setup.exe', 'browser_download_url': 'https://x/Klaus-Setup.exe'}]}
        return SimpleNamespace(status_code=200, json=lambda: d)

    def test_installiert_ohne_git(self):
        self.assertTrue(pu.installiert())

    def test_nur_neuere_version_mit_pruefsumme(self):
        with patch('requests.get', lambda *a, **k: self.api('v1.0.0')):
            self.assertIsNone(pu.neues_release())
        with patch('requests.get', lambda *a, **k: self.api(body='keine Summe')):
            self.assertIsNone(pu.neues_release())
        with patch('requests.get', lambda *a, **k: self.api()):
            self.assertEqual(pu.neues_release()['tag'], 'v1.1.0')

    def download(self, inhalt):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def raise_for_status(s): pass
            def iter_content(s, n): yield inhalt
        return lambda *a, **k: R()

    def test_falsche_pruefsumme_installiert_nichts(self):
        rel = {'tag': 'v1.1.0', 'url': 'u', 'sha256': self.hash}
        with patch('requests.get', self.download(b'boese')), patch.object(pu.subprocess, 'Popen') as popen:
            ok, text = pu.release_einspielen(rel)
        self.assertFalse(ok)
        popen.assert_not_called()
        self.assertIn('beschädigt', text)

    def test_richtige_datei_startet_stilles_update(self):
        rel = {'tag': 'v1.1.0', 'url': 'u', 'sha256': self.hash}
        with patch('requests.get', self.download(self.setup)), patch.object(pu.subprocess, 'Popen') as popen:
            ok, _ = pu.release_einspielen(rel)
        self.assertTrue(ok)
        self.assertIn('/VERYSILENT', popen.call_args[0][0])
        self.assertIn('/UPDATE=1', popen.call_args[0][0])
        self.assertIn('1.0.0 → 1.1.0', pu.nach_neustart())


if __name__ == '__main__':
    unittest.main()
