import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import stream
import stream_chatbot as bot
from assistent import CHAT_BEFEHLE, CHAT_LOS


class ChatBotTests(unittest.TestCase):
    def setUp(self):
        bot._z.update(letzte=0.0, nutzer={}, tag='', anzahl=0, spiel=('Valorant', 9e18))
        stream._z['warteschlange'].clear()
        self.auftraege = []
        self.overlay = []
        patch.object(bot, 'an', lambda: True).start()
        patch.object(stream, 'anzeigen', lambda t: None).start()
        patch.object(stream, 'overlay', lambda art, d: self.overlay.append((art, d))).start()
        # KI-Antwort vortaeuschen (mit Weckwort, Markdown und Denk-Block - muss alles raus)
        patch('ersatz_ki.chat', self._ki).start()
        patch.object(bot, '_im_hintergrund', lambda fn, *a: fn(*a)).start()   # synchron im Test
        self.addCleanup(patch.stopall)

    def _ki(self, nachrichten, **_):
        self.auftraege.append(nachrichten)
        return {'message': {'content': '<think>hmm</think>**Klaus** sagt: Diamond 2, sag freigeben!'}}

    def test_frage_wird_beantwortet_und_gefiltert(self):
        self.assertTrue(bot.befehl('lisa', 'Lisa', '!klaus welcher Rang bist du?'))
        gesagt = stream._z['warteschlange'][-1]
        self.assertIn('Diamond 2', gesagt)
        self.assertNotIn('laus', gesagt.lower())
        self.assertNotIn('freigeb', gesagt.lower())
        self.assertNotIn('think', gesagt)
        system = self.auftraege[0][0]['content']
        self.assertIn('fremden Zuschauern', system)

    def test_pausen_und_tageslimit(self):
        bot.befehl('lisa', 'Lisa', '!klaus a')
        bot.befehl('lisa', 'Lisa', '!klaus b')        # gleiche Person, gleich danach -> keine KI
        bot.befehl('max', 'Max', '!fakt')            # globale Pause -> keine KI
        self.assertEqual(len(self.auftraege), 1)
        bot._z.update(letzte=0.0, anzahl=bot.TAGESLIMIT)
        bot.befehl('tom', 'Tom', '!hype')
        self.assertEqual(len(self.auftraege), 1)

    def test_fakt_nutzt_spiel(self):
        bot.befehl('max', 'Max', '!fakt')
        self.assertIn('Valorant', self.auftraege[0][1]['content'])

    def test_ohne_ki(self):
        self.assertTrue(bot.befehl('lisa', 'Lisa', '!lurk'))
        self.assertTrue(bot.befehl('lisa', 'Lisa', '!befehle'))
        self.assertFalse(bot.befehl('lisa', 'Lisa', '!discord'))   # fremde Bot-Befehle ignorieren
        self.assertEqual(self.auftraege, [])
        self.assertEqual(self.overlay[0][0], 'hinweis')

    def test_parallel_nur_eine_ki(self):
        bot._z['arbeitet'].acquire()
        try:
            bot.befehl('lisa', 'Lisa', '!klaus hi')
        finally:
            bot._z['arbeitet'].release()
        self.assertEqual(self.auftraege, [])

    def test_zusammenfassung(self):
        stream._z['verlauf'].clear()
        self.assertIn('nichts los', bot.zusammenfassung())
        import time
        for i in range(5):
            stream._z['verlauf'].append((time.time(), f'u{i}', f'nachricht {i}'))
        with patch('ersatz_ki.text', lambda prompt: 'Lisa und Max reden über Valorant.'):
            self.assertEqual(bot.zusammenfassung(), 'Lisa und Max reden über Valorant.')

    def test_klaus_lautstaerke_befehle(self):
        from assistent import KLAUS_LAUT, STUMM
        self.assertEqual(KLAUS_LAUT.search('sprich mal etwas leiser').group('r'), 'leiser')
        self.assertEqual(KLAUS_LAUT.search('du bist zu laut').group('r2'), 'laut')
        self.assertEqual(KLAUS_LAUT.search('deine lautstärke auf 30 prozent').group('p'), '30')
        self.assertIsNone(KLAUS_LAUT.search('mach die musik leiser'))
        self.assertFalse(STUMM.search('sei leiser'))

    def test_sprachbefehle(self):
        self.assertTrue(CHAT_LOS.search('was ist im chat los'))
        self.assertTrue(CHAT_LOS.search('fass mir den chat zusammen'))
        self.assertEqual(CHAT_BEFEHLE.search('chat-befehle aus').group('an'), 'aus')


if __name__ == '__main__':
    unittest.main()
