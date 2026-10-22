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
            assert stream_overlay.starten(wache=False)

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


class KameraTests(unittest.TestCase):
    def test_maske_schraeg(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as ordner, patch.object(stream, 'MASKE', Path(ordner) / 'm.png'):
            stream._maske_bauen(100, 80, 10)
            m = Image.open(stream.MASKE)
            self.assertEqual(m.getpixel((1, 1))[3], 0)        # oben links abgeschraegt
            self.assertEqual(m.getpixel((98, 78))[3], 0)      # unten rechts abgeschraegt
            self.assertEqual(m.getpixel((98, 1))[3], 255)
            self.assertEqual(m.getpixel((50, 40))[3], 255)

    def test_sprachbefehl(self):
        from assistent import KAMERA
        self.assertEqual(KAMERA.search('kamera aus').group('an'), 'aus')
        self.assertTrue(KAMERA.search('richte die webcam ein').group('einrichten'))
        self.assertIsNone(KAMERA.search('öffne die kamera-app'))


class PauseTests(unittest.TestCase):
    def test_minuten(self):
        self.assertEqual(stream._minuten('brb 5 minuten'), 5)
        self.assertEqual(stream._minuten('stream pause zehn min'), 10)
        self.assertEqual(stream._minuten('bin eine halbe stunde weg'), 30)
        self.assertEqual(stream._minuten('eine Stunde Pause'), 60)
        self.assertIsNone(stream._minuten('brb'))

    def test_sprachbefehle(self):
        from assistent import BRB, PAUSE_ENDE
        for satz in ('brb', 'bin gleich zurück', 'stream pause', 'kurze pause', 'pause-bildschirm'):
            self.assertTrue(BRB.search(satz), satz)
        self.assertFalse(BRB.search('mach pause beim lernen'))
        self.assertTrue(PAUSE_ENDE.search('ich bin wieder da'))
        self.assertFalse(PAUSE_ENDE.search('bin gleich wieder da'))

    def test_pause_seite_wird_ausgeliefert(self):
        import http.client
        c = http.client.HTTPConnection('127.0.0.1', TEST_PORT, timeout=5)
        c.request('GET', '/pause')
        self.assertIn('Bin gleich', c.getresponse().read().decode('utf-8'))


class BannerBefehlTests(unittest.TestCase):
    def test_banner(self):
        m = STREAM_BANNER.search('zeig im Stream: gleich kommt der Bossfight!')
        self.assertEqual(m.group('text'), 'gleich kommt der Bossfight')
        self.assertTrue(STREAM_BANNER_WEG.search('banner weg'))
        self.assertFalse(STREAM_BANNER.search('zeig mir den Stream'))


if __name__ == '__main__':
    unittest.main()
