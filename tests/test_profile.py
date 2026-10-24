import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import profile_verteiler as pv


class VerteilerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        o = Path(self.tmp.name)
        for name, wert in (('ORDNER', o / 'profile'), ('EINLADUNGEN', o / 'profile' / 'einladungen.json'),
                           ('REGISTER', o / 'profile' / 'profile.json')):
            p = patch.object(pv, name, wert)
            p.start()
            self.addCleanup(p.stop)
        self.gesendet = []

        def api(methode, frist=30, **d):
            if methode == 'getMe':
                return {'username': 'KlausTestBot'}
            self.gesendet.append((methode, d))
            return {}
        for p in (patch.object(pv, '_api', api), patch.dict(os.environ, {'TESTER_BOT_TOKEN': '123:abc'})):
            p.start()
            self.addCleanup(p.stop)
        self.gestartet = []
        p = patch.object(pv.Arbeiter, 'starten', lambda a: self.gestartet.append(a.uid))
        p.start()
        self.addCleanup(p.stop)
        self.v = pv.Verteiler()

    def nachricht(self, uid, text):
        return {'update_id': 1, 'message': {'message_id': 5, 'chat': {'type': 'private'}, 'from': {'id': uid, 'first_name': 'Tim'},
                                            'text': text}}

    def code(self):
        text = pv.einladen('Tim')
        return text.split('start=')[1].split()[0]

    def test_einladung_und_profil(self):
        code = self.code()
        self.assertIn('t.me/KlausTestBot?start=', pv.einladen('X'))
        self.v.update(self.nachricht(42, f'/start {code}'))
        self.assertIn('42', json.loads(pv.REGISTER.read_text()))
        env = pv.profil_ordner(42) / '.env'
        inhalt = env.read_text()
        self.assertIn('TELEGRAM_NUTZER=42', inhalt)
        self.assertIn('KLAUS_PROFIL=1', inhalt)
        self.assertIn('KLAUS_PC_PORT=9', inhalt)            # nie Nikolas PC-Tunnel
        self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)
        self.assertEqual(self.gestartet, [42])
        self.assertIn('PIN', self.gesendet[-1][1]['text'])

    def test_code_nur_einmal_und_abgelaufen(self):
        code = self.code()
        self.v.update(self.nachricht(42, f'/start {code}'))
        self.v.update(self.nachricht(43, f'/start {code}'))
        self.assertNotIn('43', json.loads(pv.REGISTER.read_text()))
        self.assertIn('ungültig', self.gesendet[-1][1]['text'])
        alt = self.code()
        d = json.loads(pv.EINLADUNGEN.read_text())
        d[alt]['erstellt'] = time.time() - pv.CODE_GUELTIG_S - 1
        pv._schreiben(pv.EINLADUNGEN, d)
        self.v.update(self.nachricht(44, f'/start {alt}'))
        self.assertNotIn('44', json.loads(pv.REGISTER.read_text()))

    def test_fremde_werden_abgewiesen_bekannte_weitergeleitet(self):
        self.v.update(self.nachricht(7, 'hallo'))
        self.assertIn('eingeladene Tester', self.gesendet[-1][1]['text'])
        self.assertFalse(pv.ORDNER.exists() and (pv.ORDNER / '7').exists())
        code = self.code()
        self.v.update(self.nachricht(42, f'/start {code}'))
        weiter = []
        with patch.object(pv.Arbeiter, 'senden', lambda a, u: weiter.append((a.uid, u))):
            self.v.update(self.nachricht(42, 'Wie wird das Wetter?'))
            self.v.update({'update_id': 2, 'callback_query': {'from': {'id': 42}, 'data': 'ja:x'}})
        self.assertEqual([w[0] for w in weiter], [42, 42])

    def test_gesperrte_profile_werden_beendet(self):
        code = self.code()
        self.v.update(self.nachricht(42, f'/start {code}'))
        gestoppt = []
        with patch.object(pv.Arbeiter, 'stoppen', lambda a: gestoppt.append(a.uid)), \
                patch.object(pv.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='abc')):
            self.assertIn('gesperrt', pv.entfernen('42'))
            self.v.abgleich()
        self.assertEqual(gestoppt, [42])
        self.assertNotIn(42, self.v.arbeiter)

    def test_umgebung_ohne_nikolas_schluessel(self):
        a = pv.Arbeiter(42)
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'geheim', 'ALPACA_SECRET_KEY': 'geheim', 'CLAUDE_CODE_OAUTH_TOKEN': 'x'}):
            env = a.umgebung()
        self.assertEqual(env['HOME'], str(pv.profil_ordner(42)))
        self.assertFalse(any('geheim' in v or v == 'x' for v in env.values()))
        self.assertEqual(env['KLAUS_PROFIL'], '1')

    def test_code_kopie_ohne_env_und_daten(self):
        ziel = Path(self.tmp.name) / 'z'
        (ziel / 'src').mkdir(parents=True)
        (ziel / 'src' / 'alt.py').write_text('x')
        pv.code_synchronisieren(ziel)
        self.assertTrue((ziel / 'src' / 'server_gehirn.py').exists())
        self.assertFalse((ziel / 'src' / 'alt.py').exists())
        self.assertFalse((ziel / '.env').exists())


class ProfilBefehleTests(unittest.TestCase):
    def test_schluessel_und_profil(self):
        import server_gehirn as S
        import telegram_bot as TB

        tg = SimpleNamespace(befehle={}, geheime_befehle=set())
        gespeichert = {}
        with patch.object(TB, '_env_setzen', gespeichert.__setitem__), patch.object(S.os, '_exit', lambda c: None):
            S.profil_befehle(tg)
            self.assertIn('/schluessel', tg.geheime_befehle)
            self.assertIn('So:', tg.befehle['/schluessel']('/schluessel'))
            self.assertIn('kein', tg.befehle['/schluessel']('/schluessel gemini kurz').lower() + 'kein')
            self.assertIn('gespeichert', tg.befehle['/schluessel']('/schluessel Groq gsk_' + 'a' * 30))
            self.assertEqual(gespeichert, {'GROQ_API_KEY': 'gsk_' + 'a' * 30})
            self.assertIn('Luna', tg.befehle['/name']('/name Luna'))
            self.assertIn('alpaca', tg.befehle['/profil']('/profil'))

    def test_stdin_updates(self):
        import telegram_bot as TB

        bot = TB.TelegramKlaus.__new__(TB.TelegramKlaus)
        erhalten = []
        bot._update = erhalten.append
        with patch.object(sys, 'stdin', io.StringIO('{"update_id": 1}\nkaputt\n{"update_id": 2}\n')):
            bot.run_von_stdin()
        time.sleep(0.2)
        self.assertEqual(sorted(u['update_id'] for u in erhalten), [1, 2])


if __name__ == '__main__':
    unittest.main()
