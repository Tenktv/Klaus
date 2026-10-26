import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pc_update

HASH = 'a' * 64


class Antwort:
    def __init__(self, status, daten=None):
        self.status_code, self._d = status, daten or {}

    def json(self):
        return self._d


def release(tag):
    return Antwort(200, {'tag_name': tag, 'body': f'SHA256: {HASH}',
                         'assets': [{'name': 'Klaus-Setup.exe', 'url': 'api', 'browser_download_url': 'direkt'}]})


class UpdateSuchenTests(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(pc_update, 'version', lambda: '1.0.2')
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_neuere_version(self):
        with patch('requests.get', return_value=release('v1.0.5')), patch.object(pc_update, 'UPDATE_TOKEN', ''):
            rel, grund = pc_update.release_pruefen()
        self.assertEqual((rel['tag'], rel['url'], rel['sha256'], grund), ('v1.0.5', 'direkt', HASH, ''))

    def test_schon_neueste(self):
        with patch('requests.get', return_value=release('v1.0.2')):
            rel, grund = pc_update.release_pruefen()
        self.assertIsNone(rel)
        self.assertIn('neueste Version', grund)

    def test_privat_ohne_token(self):
        with patch('requests.get', return_value=Antwort(404)), patch.object(pc_update, 'UPDATE_TOKEN', ''):
            rel, grund = pc_update.release_pruefen()
        self.assertIsNone(rel)
        self.assertIn('Update-Token', grund)

    def test_ohne_pruefsumme_nichts(self):
        with patch('requests.get', return_value=Antwort(200, {'tag_name': 'v2.0.0', 'body': '', 'assets': []})):
            self.assertIsNone(pc_update.release_pruefen()[0])


if __name__ == '__main__':
    unittest.main()
