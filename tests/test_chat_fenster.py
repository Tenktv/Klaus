import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('KLAUS_LINK_TOKEN', 'x')
import server_gehirn   # noqa: F401  (stellt die PySide6-Attrappe bereit, damit assistent ohne Qt laedt)
import assistent as A


class ChatFensterTests(unittest.TestCase):
    def art(self, text):
        return 'zu' if A.CHAT_ZU.search(text) else 'auf' if A.CHAT_AUF.search(text) else '-'

    def test_oeffnen(self):
        for t in ('mach den Chat auf', 'öffne das Chatfenster', 'zeig mir den Chat', 'Chat öffnen', 'mach mir ein Chatfenster auf'):
            self.assertEqual(self.art(t), 'auf', t)

    def test_schliessen(self):
        for t in ('mach den Chat zu', 'schließ das Chatfenster', 'Chat zu', 'chatfenster schließen', 'mach den chat weg'):
            self.assertEqual(self.art(t), 'zu', t)

    def test_nicht_ausloesen(self):
        for t in ('lies mir den Twitch chat vor', 'was steht im chat', 'ich chatte gleich mit Tim', 'schließ das Fenster von Chrome'):
            self.assertEqual(self.art(t), '-', t)

    def test_werkzeug_sendet_signal(self):
        import gemini_live

        g = gemini_live.GeminiGespraech.__new__(gemini_live.GeminiGespraech)
        gesendet = []
        g.a = type('A', (), {'b': type('B', (), {'chat_fenster': type('S', (), {'emit': staticmethod(gesendet.append)})()})()})()
        g.gefunden, g.ende = set(), False
        self.assertIn('offen', g._werkzeug('chat_fenster', {'aktion': 'oeffnen'}))
        self.assertIn('zu', g._werkzeug('chat_fenster', {'aktion': 'schliessen'}))
        self.assertEqual(gesendet, [True, False])
        self.assertIn('chat_fenster', [w['name'] for w in gemini_live.WERKZEUGE])

    def test_stimmen_werkzeug_erreichbar(self):
        import gemini_live
        import stimmwahl

        g = gemini_live.GeminiGespraech.__new__(gemini_live.GeminiGespraech)
        g.a = type('A', (), {'b': None})()
        g.gefunden, g.ende = set(), False
        with patch.object(stimmwahl, 'liste_text', lambda: 'LISTE'), patch.object(stimmwahl, 'waehlen', lambda n: f'GEWAEHLT {n}'):
            self.assertEqual(g._werkzeug('stimme', {'aktion': 'zeigen'}), 'LISTE')
            self.assertEqual(g._werkzeug('stimme', {'aktion': 'wechseln', 'name': 'Sensei'}), 'GEWAEHLT Sensei')


if __name__ == '__main__':
    unittest.main()
