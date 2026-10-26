import os
import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('KLAUS_LINK_TOKEN', 'x')
import server_gehirn   # noqa: F401  (PySide6-Attrappe)
import gemini_live
import stimmwahl


class StimmAusfallTests(unittest.TestCase):
    def tearDown(self):
        stimmwahl._ausfall['bis'] = 0.0

    def test_fish_kaputt_gemini_spricht_trotzdem(self):
        g = gemini_live.GeminiGespraech.__new__(gemini_live.GeminiGespraech)
        meldungen = []
        g.a = type('A', (), {'darf_sprechen': lambda self, q: True,
                             'b': type('B', (), {'meldung': type('S', (), {'emit': staticmethod(meldungen.append)})(),
                                                 'zustand': type('S', (), {'emit': staticmethod(lambda z: None)})()})()})()
        g.fish_saetze, g.wiedergabe = queue.Queue(), queue.Queue()
        g.fish_runde, g.fish_an, g.fish_arbeitet, g._zustand = 0, True, False, ''
        g.gemini_audio = [b'gemini-1', b'gemini-2']

        def kaputt(satz):
            raise RuntimeError('Fish Audio 402 kein Guthaben')
            yield b''
        with patch.object(stimmwahl, 'pcm_strom', kaputt), patch.object(stimmwahl, 'aktiv', lambda: {'name': 'Gojo', 'art': 'fish'}):
            threading.Thread(target=g._fish_sprecher, daemon=True).start()
            g.fish_saetze.put((0, 'Hallo, wie geht es dir?'))
            ende = time.time() + 2
            while g.wiedergabe.qsize() < 2 and time.time() < ende:
                time.sleep(0.01)
        self.assertEqual([g.wiedergabe.get_nowait(), g.wiedergabe.get_nowait()], [b'gemini-1', b'gemini-2'])
        self.assertFalse(g.fish_an)
        self.assertTrue(stimmwahl.extern_gesperrt())   # naechstes Gespraech gleich mit Gemini-Stimme
        self.assertIn('Gojo', meldungen[0])

    def test_neue_stimme_hebt_sperre_auf(self):
        stimmwahl.extern_sperren('test')
        self.assertTrue(stimmwahl.extern_gesperrt())
        stimmwahl._ausfall['bis'] = 0.0
        self.assertFalse(stimmwahl.extern_gesperrt())


if __name__ == '__main__':
    unittest.main()
