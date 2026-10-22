import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import stream


def notice(tags: str, text: str = '') -> dict:
    return stream.parse_zeile(f'@{tags} :tmi.twitch.tv USERNOTICE #lateniko' + (f' :{text}' if text else ''))


class DankeTests(unittest.TestCase):
    def setUp(self):
        stream._z['warteschlange'].clear()
        stream._z['gesehen'].clear()
        stream._z['geschenke'].clear()
        self.overlay = []
        patch.object(stream, 'overlay', lambda art, d: self.overlay.append((art, d))).start()
        patch.object(stream, 'anzeigen', lambda t: None).start()
        patch.object(stream, 'vorlesen_an', lambda: False).start()   # Dank kommt trotzdem
        patch('stream.random.choice', lambda liste: liste[0]).start()
        self.addCleanup(patch.stopall)

    def gesagt(self):
        return list(stream._z['warteschlange'])

    def test_sub_und_resub(self):
        stream._ereignis(notice('display-name=Lisa_23;login=lisa_23;msg-id=sub'), 'lateniko')
        stream._ereignis(notice('display-name=Max;login=max;msg-id=resub;msg-param-cumulative-months=7', 'immer noch da'), 'lateniko')
        self.assertEqual(self.gesagt(), ['Wow, Lisa hat abonniert – vielen Dank!', 'Max ist seit 7 Monaten dabei – danke für den Resub!'])
        self.assertEqual(self.overlay[0], ('hinweis', {'kopf': 'Neues Abo', 'text': 'Wow, Lisa_23 hat abonniert – vielen Dank!', 'art': 'danke'}))

    def test_verschenkte_abos_nur_einmal(self):
        stream._ereignis(notice('display-name=Tom;login=tom;msg-id=submysterygift;msg-param-mass-gift-count=5'), 'lateniko')
        for i in range(5):
            stream._ereignis(notice(f'display-name=Tom;login=tom;msg-id=subgift;msg-param-recipient-display-name=u{i}'), 'lateniko')
        self.assertEqual(self.gesagt(), ['Tom verschenkt 5 Abos – Wahnsinn, danke!'])
        stream._ereignis(notice('display-name=Tom;login=tom;msg-id=subgift;msg-param-recipient-display-name=Anna'), 'lateniko')
        self.assertEqual(self.gesagt()[-1], 'Tom verschenkt ein Abo an Anna. Danke!')

    def test_raid_und_bits(self):
        stream._ereignis(notice('display-name=GroßerStreamer;login=gs;msg-id=raid;msg-param-displayName=GroßerStreamer;msg-param-viewerCount=42'), 'lateniko')
        stream._ereignis(stream.parse_zeile('@display-name=Lisa;bits=100 :lisa!lisa@x PRIVMSG #lateniko :cheer100 gg'), 'lateniko')
        self.assertEqual(self.gesagt()[0], 'Raid! GroßerStreamer kommt mit 42 Leuten vorbei. Willkommen, alle zusammen!')
        self.assertIn('Lisa schickt 100 Bits – danke!', self.gesagt())

    def test_name_mit_klaus_wird_nicht_zum_befehl(self):
        stream._ereignis(notice('display-name=KlausFan;login=klausfan;msg-id=sub'), 'lateniko')
        self.assertNotIn('laus', self.gesagt()[0].lower())

    def test_follower_nur_neue_und_nicht_beim_start(self):
        antworten = [
            {'total': 2, 'data': [{'user_id': '2', 'user_name': 'B'}, {'user_id': '1', 'user_name': 'A'}]},
            {'total': 3, 'data': [{'user_id': '3', 'user_name': 'Neu_1'}, {'user_id': '2', 'user_name': 'B'}]},
        ]
        def helix(*_a, **_k):
            r = MagicMock()
            r.json.return_value = antworten.pop(0) if antworten else {'data': []}
            return r
        schlaf = MagicMock(side_effect=[None, None, StopIteration])
        with patch.object(stream, '_scopes', lambda: {'moderator:read:followers'}), patch.object(stream, '_helix', helix), \
                patch.object(stream, '_sender_id', lambda: '99'), patch.object(stream.time, 'sleep', schlaf):
            with self.assertRaises(StopIteration):
                stream._follower_wache()
        self.assertEqual(self.gesagt(), ['Danke für den Follow, Neu!'])


if __name__ == '__main__':
    unittest.main()
