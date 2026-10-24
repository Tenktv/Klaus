import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import llm


def kein_ollama(*a, **k):
    raise requests.ConnectionError('kein Ollama')


class LlmErsatzTests(unittest.TestCase):
    def test_ohne_ollama_antwortet_die_cloud_ki(self):
        fake = SimpleNamespace(bereit=lambda: True, chat=lambda n: {'message': {'content': 'Hallo aus Groq'}})
        with patch.object(llm.requests, 'post', kein_ollama), patch.dict(sys.modules, {'ersatz_ki': fake}):
            self.assertEqual(llm.chat([{'role': 'user', 'content': 'hi'}]), 'Hallo aus Groq')

    def test_json_aus_cloud_antwort(self):
        fake = SimpleNamespace(bereit=lambda: True, chat=lambda n: {'message': {'content': 'Klar: {"ok": true} fertig'}})
        with patch.object(llm.requests, 'post', kein_ollama), patch.dict(sys.modules, {'ersatz_ki': fake}):
            self.assertEqual(llm.frage('x', als_json=True), {'ok': True})

    def test_ohne_alles_klarer_fehler(self):
        fake = SimpleNamespace(bereit=lambda: False, chat=None)
        with patch.object(llm.requests, 'post', kein_ollama), patch.dict(sys.modules, {'ersatz_ki': fake}):
            with self.assertRaises(requests.RequestException):
                llm.chat([{'role': 'user', 'content': 'hi'}])

    def test_ollama_hat_vorrang(self):
        antwort = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'message': {'content': ' lokal '}})
        with patch.object(llm.requests, 'post', lambda *a, **k: antwort):
            self.assertEqual(llm.chat([{'role': 'user', 'content': 'hi'}]), 'lokal')


if __name__ == '__main__':
    unittest.main()
