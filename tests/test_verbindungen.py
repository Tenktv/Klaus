import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('KLAUS_LINK_TOKEN', 'x')
import server_gehirn   # noqa: F401  (PySide6-Attrappe, damit assistent ohne Qt laedt)
import assistent as A
import freigabe
import stream
import verbindungen as V
import youtube

SCHLUESSEL = ['TWITCH_KANAL', 'TWITCH_CLIENT_ID', 'TWITCH_CLIENT_SECRET', 'YOUTUBE_KANAL', 'YOUTUBE_API_KEY', 'X_API_KEY',
              'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_SECRET', 'INSTAGRAM_KONTO_ID', 'INSTAGRAM_TOKEN', 'DISCORD_WEBHOOK']
DISCORD = 'https://discord.com/api/webhooks/123456/abcDEF-ghi_jkl'


class Antwort:
    def __init__(self, status=200, daten=None):
        self.status_code, self._daten, self.text = status, daten or {}, str(daten)

    def json(self):
        return self._daten


def token(art='posten'):
    t = f'test-{time.time()}'
    freigabe._tokens[t] = (art, time.time())
    return t


class VerbindungenTests(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.env = Path(self.ordner.name) / '.env'
        self.env.write_text('KLAUS_NAME=Luna\nTWITCH_KANAL=alt\n', encoding='utf-8')
        self.vorher = {k: v for k, v in os.environ.items() if k in SCHLUESSEL or k.startswith('WEBHOOK_')}
        for k in list(os.environ):
            if k in SCHLUESSEL or k.startswith('WEBHOOK_'):
                del os.environ[k]
        self.patches = [patch.object(V, 'ENV_DATEI', self.env), patch.object(stream, 'neu_laden', lambda: ''),
                        patch.object(stream, 'TOKEN_DATEI', Path(self.ordner.name) / 'twitch_token.json')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for k in list(os.environ):
            if k in SCHLUESSEL or k.startswith('WEBHOOK_'):
                del os.environ[k]
        os.environ.update(self.vorher)
        self.ordner.cleanup()

    def test_oauth1_signatur_wie_in_der_x_doku(self):
        kopf = V.oauth1_kopf('POST', 'https://api.twitter.com/1.1/statuses/update.json',
                             'xvz1evFS4wEEPTGEFPHBog', 'kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw',
                             '370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb', 'LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE',
                             params={'include_entities': 'true', 'status': 'Hello Ladies + Gentlemen, a signed OAuth request!'},
                             nonce='kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg', zeit='1318622958')
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', kopf)

    def test_normalisieren(self):
        self.assertEqual(V.normalisieren('TWITCH_KANAL', 'https://www.twitch.tv/MeinKanal/'), 'meinkanal')
        self.assertEqual(V.normalisieren('YOUTUBE_KANAL', 'https://youtube.com/@Mein.Kanal'), '@Mein.Kanal')
        self.assertEqual(V.normalisieren('YOUTUBE_KANAL', 'meinkanal'), '@meinkanal')
        self.assertEqual(V.normalisieren('X_API_KEY', '  abc\n'), 'abc')
        for env, wert in [('TWITCH_KANAL', 'a b'), ('DISCORD_WEBHOOK', 'https://evil.com/api/webhooks/1/x'),
                          ('_URL', 'http://example.com/hook'), ('INSTAGRAM_KONTO_ID', '12ab'), ('X_API_KEY', 'ab cd')]:
            with self.assertRaises(ValueError, msg=wert):
                V.normalisieren(env, wert)
        self.assertEqual(V.normalisieren('_URL', 'http://localhost:5678/webhook/x'), 'http://localhost:5678/webhook/x')

    def test_speichern_schreibt_env_und_behaelt_rest(self):
        text = V.speichern('twitch', {'TWITCH_KANAL': 'twitch.tv/NeuerKanal', 'TWITCH_CLIENT_SECRET': ''})
        inhalt = self.env.read_text(encoding='utf-8')
        self.assertIn('KLAUS_NAME=Luna', inhalt)
        self.assertIn('TWITCH_KANAL=neuerkanal', inhalt)
        self.assertNotIn('TWITCH_KANAL=alt', inhalt)
        self.assertNotIn('TWITCH_CLIENT_SECRET', inhalt)   # leer = nicht angefasst
        self.assertEqual(os.environ['TWITCH_KANAL'], 'neuerkanal')
        self.assertEqual(V.zustand('twitch'), 'ja')
        self.assertIn('gespeichert', text)

    def test_zustand_und_trennen(self):
        self.assertEqual(V.zustand('x'), 'nein')
        V.speichern('x', {'X_API_KEY': 'k', 'X_API_SECRET': 's'})
        self.assertEqual(V.zustand('x'), 'teilweise')
        V.speichern('x', {'X_ACCESS_TOKEN': 't', 'X_ACCESS_SECRET': 'g'})
        self.assertEqual(V.zustand('x'), 'ja')
        V.trennen('x')
        self.assertEqual(V.zustand('x'), 'nein')
        self.assertIn('X_API_KEY=\n', self.env.read_text(encoding='utf-8'))

    def test_twitch_clips_halb_ohne_anmeldung(self):
        V.speichern('twitch', {'TWITCH_KANAL': 'kanal', 'TWITCH_CLIENT_ID': 'abc123'})
        self.assertEqual(V.zustand('twitch'), 'teilweise')
        stream.TOKEN_DATEI.write_text('{}')
        self.assertEqual(V.zustand('twitch'), 'ja')

    def test_webhook_eigene_plattform(self):
        V.speichern('webhook', {'_NAME': 'LinkedIn', '_URL': 'https://hooks.zapier.com/hooks/catch/1/abc/'})
        self.assertEqual(os.environ['WEBHOOK_LINKEDIN'], 'https://hooks.zapier.com/hooks/catch/1/abc/')
        self.assertEqual(V.finde('linkedin'), 'webhook:Linkedin')
        self.assertIn('Linkedin', V.kann_posten())
        with self.assertRaises(ValueError):
            V.speichern('webhook', {'_NAME': 'Twitter', '_URL': 'https://hooks.zapier.com/x'})   # dafuer gibt's X
        with patch('requests.post', return_value=Antwort(200)) as post:
            self.assertIn('geschickt', V.posten('webhook:Linkedin', 'Hallo Welt', token()))
        self.assertEqual(post.call_args.kwargs['json']['text'], 'Hallo Welt')

    def test_finde(self):
        self.assertEqual(V.finde('Twitter'), 'x')
        self.assertEqual(V.finde('insta'), 'instagram')
        self.assertEqual(V.finde('YouTube'), 'youtube')
        self.assertEqual(V.finde('tiktok'), '')

    def test_posten_nur_mit_freigabe(self):
        V.speichern('discord', {'DISCORD_WEBHOOK': DISCORD})
        with patch('requests.post', return_value=Antwort(204)) as post:
            with self.assertRaises(PermissionError):
                V.posten('discord', 'Ich bin live!', 'falsch')
            with self.assertRaises(PermissionError):
                V.posten('discord', 'Ich bin live!', token('clip'))
            post.assert_not_called()
            self.assertIn('Discord', V.posten('discord', 'Ich bin live!', token()))
        self.assertEqual(post.call_args.kwargs['json']['allowed_mentions'], {'parse': []})

    def test_posten_pruefen(self):
        self.assertIn('nicht verbunden', V.posten_pruefen('x', 'hi'))
        V.speichern('x', {'X_API_KEY': 'k', 'X_API_SECRET': 's', 'X_ACCESS_TOKEN': 't', 'X_ACCESS_SECRET': 'g'})
        self.assertEqual(V.posten_pruefen('x', 'hi'), '')
        self.assertIn('280', V.posten_pruefen('x', 'a' * 281))
        self.assertIn('Wo soll ich posten', V.posten_pruefen('', 'hi'))
        self.assertIn('nicht posten', V.posten_pruefen('youtube', 'hi'))
        V.speichern('instagram', {'INSTAGRAM_KONTO_ID': '1789', 'INSTAGRAM_TOKEN': 'tok'})
        self.assertIn('Bild', V.posten_pruefen('instagram', 'hi'))
        self.assertEqual(V.posten_pruefen('instagram', 'hi', 'https://bilder.example/a.jpg'), '')

    def test_x_posten_signiert(self):
        V.speichern('x', {'X_API_KEY': 'k', 'X_API_SECRET': 's', 'X_ACCESS_TOKEN': 't', 'X_ACCESS_SECRET': 'g'})
        with patch('requests.post', return_value=Antwort(201, {'data': {'id': '42'}})) as post:
            self.assertIn('x.com/i/status/42', V.posten('x', 'Stream startet gleich', token()))
        self.assertTrue(post.call_args.kwargs['headers']['Authorization'].startswith('OAuth oauth_consumer_key="k"'))

    def test_status_text_ohne_geheimnisse(self):
        V.speichern('youtube', {'YOUTUBE_KANAL': '@kanal', 'YOUTUBE_API_KEY': 'GEHEIM123'})
        text = V.status_text()
        self.assertIn('YouTube: verbunden (@kanal)', text)
        self.assertNotIn('GEHEIM123', text)


class StreamYouTubeTests(unittest.TestCase):
    def setUp(self):
        stream._z['gesehen'].clear()
        stream._z['verlauf'].clear()
        self.gemeldet = []
        self.p = patch.object(stream, '_melden', lambda g, a, vorlesen_immer=False: self.gemeldet.append((g, vorlesen_immer)))
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_youtube_nachrichten_wie_twitch(self):
        n = {'snippet': {'type': 'textMessageEvent', 'displayMessage': 'Hallo Klaus, freigeben!'},
             'authorDetails': {'displayName': 'Max_99', 'channelId': 'UC1', 'isChatOwner': False}}
        youtube.verarbeite(n, stream)
        youtube.verarbeite(n, stream)
        self.assertEqual(len(self.gemeldet), 2)
        self.assertTrue(self.gemeldet[0][1])                # neu -> Gruss, immer vorlesen
        self.assertNotIn('freigeben', self.gemeldet[1][0])   # Freigabe-Woerter aus fremdem Chat entfernt
        self.assertNotIn('Klaus', self.gemeldet[1][0])
        self.assertIn('youtube:UC1', stream._z['gesehen'])

    def test_eigene_nachricht_nicht_vorlesen(self):
        youtube.verarbeite({'snippet': {'type': 'textMessageEvent', 'displayMessage': 'test'},
                            'authorDetails': {'displayName': 'Ich', 'channelId': 'UC0', 'isChatOwner': True}}, stream)
        self.assertEqual(self.gemeldet, [])

    def test_super_chat_danke(self):
        youtube.verarbeite({'snippet': {'type': 'superChatEvent', 'superChatDetails': {'amountDisplayString': '5,00 €'}},
                            'authorDetails': {'displayName': 'Anna'}}, stream)
        self.assertIn('5,00 €', self.gemeldet[0][0])

    def test_youtube_kanal_normalisieren(self):
        self.assertEqual(youtube.normalisieren('UC' + 'a' * 22), 'UC' + 'a' * 22)
        self.assertEqual(youtube.normalisieren('https://www.youtube.com/channel/UC' + 'b' * 22), 'UC' + 'b' * 22)
        with self.assertRaises(ValueError):
            youtube.normalisieren('x')


class SpracheUndWerkzeugTests(unittest.TestCase):
    def test_verbinden_erkannt(self):
        for t, p in [('verbinde Twitch', 'Twitch'), ('verbinde mich mit YouTube', 'YouTube'), ('Klaus, verknüpfe mein Instagram', 'Instagram'),
                     ('verbinde dich mit x', 'x'), ('koppel TikTok', 'TikTok'), ('öffne die Verbindungen', None)]:
            m = A.VERBINDEN.search(t)
            self.assertTrue(m, t)
            self.assertEqual(m.group('p'), p, t)
        for t in ('verbinde die Kopfhörer per Bluetooth', 'welche Verbindungen gibt es nach Berlin', 'lies den Twitch chat vor'):
            self.assertFalse(A.VERBINDEN.search(t), t)

    def test_posten_werkzeug_fragt_freigabe(self):
        import gemini_live

        g = gemini_live.GeminiGespraech.__new__(gemini_live.GeminiGespraech)
        gefragt = []
        g.a = type('A', (), {'b': None, '_mit_freigabe': lambda self, art, was, f, an='': gefragt.append((art, was, an)) or 'FRAGE'})()
        g.gefunden, g.ende = set(), False
        with patch.object(V, 'zustand', lambda pid: 'ja'):
            self.assertEqual(g._werkzeug('posten', {'plattform': 'Discord', 'text': 'Bin live'}), 'FRAGE')
        self.assertEqual(gefragt[0][0], 'posten')
        self.assertEqual(gefragt[0][2], 'Discord')
        namen = [w['name'] for w in gemini_live.WERKZEUGE]
        for n in ('verbindungen', 'posten', 'youtube'):
            self.assertIn(n, namen)


if __name__ == '__main__':
    unittest.main()
