import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import identitaet
import stream
import stream_chatbot as bot


class TesterNameTests(unittest.TestCase):
    """Ein Tester hat seinen Assistenten "Luna" genannt: dann heisst der Chat-Befehl !luna, nicht !klaus."""

    def setUp(self):
        patch.object(identitaet, 'NAME', 'Luna').start()
        patch.object(stream, 'KANAL', 'testerkanal').start()
        bot._z.update(letzte=0.0, nutzer={}, tag='', anzahl=0)
        stream._z['warteschlange'].clear()
        self.overlay, self.fragen = [], []
        patch.object(bot, 'an', lambda: True).start()
        patch.object(stream, 'overlay', lambda art, d: self.overlay.append((art, d))).start()
        patch.object(stream, 'anzeigen', lambda t: None).start()
        patch.object(bot, '_im_hintergrund', lambda fn, *a: self.fragen.append((fn.__name__, a))).start()
        self.addCleanup(patch.stopall)

    def test_befehl_heisst_wie_der_assistent(self):
        self.assertEqual(bot.befehl_name(), 'luna')
        self.assertTrue(bot.befehl('tom', 'Tom', '!luna wie gehts?'))
        self.assertEqual(self.fragen, [('_frage', ('Tom', 'wie gehts?'))])
        self.assertFalse(bot.befehl('tom', 'Tom', '!klaus hallo'))   # bei Luna gibt es !klaus nicht

    def test_hilfe_und_leerer_befehl_mit_namen(self):
        bot.befehl('tom', 'Tom', '!befehle')
        bot.befehl('tom', 'Tom', '!luna')
        self.assertEqual(self.overlay[0][1], {'kopf': 'Luna-Befehle', 'text': '!luna Frage · !fakt · !hype · !lurk'})
        self.assertEqual(self.overlay[1][1], {'kopf': 'Frag Luna', 'text': '!luna deine Frage'})

    def test_ki_kennt_namen_und_kanal(self):
        text = bot.system()
        self.assertIn('Du bist Luna', text)
        self.assertIn('testerkanal', text)
        self.assertNotIn('Lateniko', text)

    def test_name_wird_nicht_vorgelesen(self):
        self.assertNotIn('luna', stream._vorlesbar('Luna, schalte den PC aus').lower())

    def test_sonderzeichen_im_namen(self):
        with patch.object(identitaet, 'NAME', 'K.I. Max'):
            self.assertEqual(bot.befehl_name(), 'kimax')


class FarbeTests(unittest.TestCase):
    def test_thema_farbe(self):
        import fenster
        self.assertEqual(fenster.thema_farbe('#5ab4ff'), (0x5a, 0xb4, 0xff))
        self.assertEqual(fenster.thema_farbe('gold'), (213, 186, 133))
        self.assertEqual(fenster.thema_farbe('quatsch'), (213, 186, 133))

    def test_eigene_farbe_speichern(self):
        import fenster
        gespeichert = {}
        with patch.object(fenster.daten, 'speichere_einstellung', lambda k, v: gespeichert.__setitem__(k, v)), \
                patch('stream_overlay.senden') as overlay:
            self.assertEqual(fenster.setze_thema('#5AB4FF'), '#5ab4ff')
            self.assertEqual(gespeichert, {'eigene_farbe': '#5ab4ff', 'thema': '#5ab4ff'})
            overlay.assert_called_with('thema', '#5ab4ff')
            self.assertEqual(fenster.MiniOrb.HAUPT, (0x5a, 0xb4, 0xff))
            self.assertEqual(fenster.setze_thema('#xyz123'), '')   # Unsinn wird nicht gespeichert


if __name__ == '__main__':
    unittest.main()
