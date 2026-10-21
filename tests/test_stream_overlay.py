import http.client
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import stream
import stream_overlay
from assistent import STREAM_BANNER, STREAM_BANNER_WEG

TEST_PORT = 7719


class OverlayServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(stream_overlay, 'PORT', TEST_PORT):
            assert stream_overlay.starten()

    def _get(self, pfad):
        c = http.client.HTTPConnection('127.0.0.1', TEST_PORT, timeout=5)
        c.request('GET', pfad)
        return c.getresponse()

    def test_seite_und_orb_skript(self):
        self.assertIn(b'KlausOrb', self._get('/overlay').read())
        self.assertEqual(self._get('/klaus.js').status, 200)

    def test_nichts_ausserhalb_von_web(self):
        for pfad in ('/../stream.py', '/..%2F..%2F.env', '/../../.env'):
            self.assertEqual(self._get(pfad).status, 404, pfad)

    def test_ereignisse_kommen_an(self):
        antwort = self._get('/ereignisse')
        self.assertEqual(antwort.getheader('Content-Type').split(';')[0], 'text/event-stream')
        gelesen = []

        def lesen():
            while b'event: chat' not in b''.join(gelesen):
                gelesen.append(antwort.fp.read1(4096))

        leser = threading.Thread(target=lesen, daemon=True)
        leser.start()
        time.sleep(0.3)
        stream_overlay.senden('chat', {'name': 'Lisa', 'text': '<b>hi</b>', 'farbe': '', 'neu': True})
        leser.join(3)
        roh = b''.join(gelesen).decode('utf-8')
        self.assertIn('event: thema', roh)
        self.assertIn('event: chat', roh)
        self.assertIn('<b>hi</b>', roh)   # Rohtext; die Seite setzt ihn nur per textContent

    def test_pegel_gedrosselt(self):
        with patch.object(stream_overlay, '_hoerer', []):
            stream_overlay.senden('pegel', 0.5)
            t = stream_overlay._zuletzt['pegel']
            stream_overlay.senden('pegel', 0.6)
            self.assertEqual(stream_overlay._zuletzt['pegel'], t)


class OverlayChatTests(unittest.TestCase):
    def setUp(self):
        stream._z['gesehen'].clear()
        self.ereignisse = []
        patch.object(stream, 'overlay', lambda art, d: self.ereignisse.append((art, d))).start()
        patch.object(stream, 'anzeigen', lambda t: None).start()
        patch.object(stream, 'vorlesen_an', lambda: False).start()
        self.addCleanup(patch.stopall)

    def test_eigene_nachricht_im_overlay_aber_nicht_vorgelesen(self):
        stream._ereignis(stream.parse_zeile('@display-name=Lateniko;color=#FF0000 :lateniko!x@x PRIVMSG #lateniko :gg'), 'lateniko')
        self.assertEqual(self.ereignisse, [('chat', {'name': 'Lateniko', 'text': 'gg', 'farbe': '#FF0000', 'neu': False})])

    def test_neuer_zuschauer_bekommt_willkommen(self):
        stream._ereignis(stream.parse_zeile(':lisa!x@x PRIVMSG #lateniko :hi'), 'lateniko')
        self.assertEqual([a for a, _ in self.ereignisse], ['chat', 'willkommen'])


class BannerBefehlTests(unittest.TestCase):
    def test_banner(self):
        m = STREAM_BANNER.search('zeig im Stream: gleich kommt der Bossfight!')
        self.assertEqual(m.group('text'), 'gleich kommt der Bossfight')
        self.assertTrue(STREAM_BANNER_WEG.search('banner weg'))
        self.assertFalse(STREAM_BANNER.search('zeig mir den Stream'))


if __name__ == '__main__':
    unittest.main()
