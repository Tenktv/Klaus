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
        self.gesendet, self.geloescht = [], []

        def api(methode, frist=30, **d):
            if methode == 'getMe':
                return {'username': 'KlausTestBot'}
            (self.geloescht if methode == 'deleteMessage' else self.gesendet).append(d)
            return {}
        for p in (patch.object(pv, '_api', api), patch.dict(os.environ, {'TESTER_BOT_TOKEN': '123:abc'})):
            p.start()
            self.addCleanup(p.stop)
        self.gestartet = []
        for p in (patch.object(pv.Arbeiter, 'starten', lambda a: self.gestartet.append(a.name)),
                  patch.object(pv.Arbeiter, 'laeuft', lambda a: True)):
            p.start()
            self.addCleanup(p.stop)
        self.v = pv.Verteiler()

    def msg(self, uid, text, mid=5):
        return {'update_id': 1, 'message': {'message_id': mid, 'chat': {'type': 'private', 'id': uid},
                                            'from': {'id': uid, 'first_name': 'Tim'}, 'text': text}}

    def letzte(self):
        return self.gesendet[-1]['text']

    def anlegen(self, uid=42, name='tim', pw='Geheim123'):
        code = pv.einladen('Tim').split('start=')[1].split()[0]
        self.v.update(self.msg(uid, f'/start {code}'))
        self.v.update(self.msg(uid, f'{name} {pw}', mid=6))

    def test_einladung_profilname_passwort(self):
        self.anlegen()
        r = json.loads(pv.REGISTER.read_text())
        self.assertEqual(r['tim']['telegram'], 42)
        self.assertNotIn('Geheim123', pv.REGISTER.read_text())           # nur Hash
        self.assertIn({'chat_id': 42, 'message_id': 6}, self.geloescht)   # Passwort-Nachricht geloescht
        env = pv.profil_ordner('tim') / '.env'
        self.assertIn('TELEGRAM_NUTZER=42', env.read_text())
        self.assertIn('KLAUS_PC_PORT=9', env.read_text())
        if os.name != 'nt':   # Unix-Dateirechte gibt es unter Windows so nicht (der Verteiler laeuft auf dem Linux-Server)
            self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)
        self.assertIn('tim', self.gestartet)
        self.assertIn('PIN', self.letzte())

    def test_schwaches_passwort_und_vergebener_name(self):
        code = pv.einladen().split('start=')[1].split()[0]
        self.v.update(self.msg(42, f'/start {code}'))
        self.v.update(self.msg(42, 'tim kurz'))
        self.assertIn('8 Zeichen', self.letzte())
        self.v.update(self.msg(42, 'Tim! Geheim123'))
        self.assertIn('a–z', self.letzte())
        self.v.update(self.msg(42, 'tim Geheim123'))
        self.assertIn('tim', json.loads(pv.REGISTER.read_text()))
        code2 = pv.einladen().split('start=')[1].split()[0]
        self.v.update(self.msg(43, f'/start {code2}'))
        self.v.update(self.msg(43, 'tim Anders456'))
        self.assertIn('vergeben', self.letzte())

    def test_code_nur_einmal(self):
        code = pv.einladen().split('start=')[1].split()[0]
        self.v.update(self.msg(42, f'/start {code}'))
        self.v.update(self.msg(42, 'tim Geheim123'))
        self.v.update(self.msg(43, f'/start {code}'))
        self.assertIn('ungültig', self.letzte())

    def test_login_von_anderem_konto_und_warnung(self):
        self.anlegen()
        self.v.update(self.msg(99, '/login tim Geheim123', mid=9))
        self.assertIn({'chat_id': 99, 'message_id': 9}, self.geloescht)
        r = json.loads(pv.REGISTER.read_text())
        self.assertEqual(r['tim']['telegram'], 99)
        self.assertIn('TELEGRAM_NUTZER=99', (pv.profil_ordner('tim') / '.env').read_text())
        warnungen = [g for g in self.gesendet if g['chat_id'] == 42 and 'anderen Telegram-Konto' in g['text']]
        self.assertEqual(len(warnungen), 1)
        weiter = []
        with patch.object(pv.Arbeiter, 'senden', lambda a, u: weiter.append(a.name)):
            self.v.update(self.msg(99, 'Wie wird das Wetter?'))
            self.v.update(self.msg(42, 'Hallo?'))                       # altes Konto ist abgemeldet
        self.assertEqual(weiter, ['tim'])
        self.assertIn('/login', self.letzte())

    def test_falsches_passwort_sperrt_nach_fuenf(self):
        self.anlegen()
        for _ in range(5):
            self.v.update(self.msg(77, '/login tim Falsch999'))
        self.assertIn('stimmt nicht', self.gesendet[-1]['text'])
        self.v.update(self.msg(77, '/login tim Geheim123'))
        self.assertIn('gesperrt', self.letzte())
        self.assertEqual(json.loads(pv.REGISTER.read_text())['tim']['telegram'], 42)
        self.v.update(self.msg(78, '/login tim Geheim123'))              # Profil selbst ist auch gesperrt
        self.assertIn('gesperrt', self.letzte())

    def test_logout_und_passwort_aendern(self):
        self.anlegen()
        self.v.update(self.msg(42, '/passwort Falsch999 Neu12345'))
        self.assertIn('stimmt nicht', self.letzte())
        self.v.update(self.msg(42, '/passwort Geheim123 Neu12345'))
        self.assertIn('geändert', self.letzte())
        self.v.update(self.msg(42, '/logout'))
        self.assertIsNone(json.loads(pv.REGISTER.read_text())['tim']['telegram'])
        self.assertIn('TELEGRAM_NUTZER=0', (pv.profil_ordner('tim') / '.env').read_text())
        self.v.update(self.msg(42, '/login tim Geheim123'))
        self.assertIn('stimmt nicht', self.letzte())
        self.v.update(self.msg(42, '/login tim Neu12345'))
        self.assertIn('Angemeldet', self.letzte())

    def test_fremde_und_gesperrte_profile(self):
        self.v.update(self.msg(7, 'hallo'))
        self.assertIn('/login', self.letzte())
        self.anlegen()
        gestoppt = []
        with patch.object(pv.Arbeiter, 'stoppen', lambda a: gestoppt.append(a.name)), \
                patch.object(pv.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='abc')):
            self.assertIn('gesperrt', pv.entfernen('tim'))
            self.v.abgleich()
        self.assertEqual(gestoppt, ['tim'])
        self.v.update(self.msg(42, 'hallo'))
        self.assertIn('/login', self.letzte())

    def test_ungueltige_namen_nie_als_pfad(self):
        with self.assertRaises(ValueError):
            pv.profil_ordner('../nikola')

    def test_umgebung_ohne_nikolas_schluessel(self):
        a = pv.Arbeiter('tim')
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'geheim', 'ALPACA_SECRET_KEY': 'geheim', 'CLAUDE_CODE_OAUTH_TOKEN': 'x'}):
            env = a.umgebung()
        self.assertEqual(env['HOME'], str(pv.profil_ordner('tim')))
        self.assertFalse(any('geheim' in v or v == 'x' for v in env.values()))

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
        gespeichert, neustarts = {}, []
        with patch.object(TB, '_env_setzen', gespeichert.__setitem__), patch.object(S, 'profil_neustart', lambda: neustarts.append(1)):
            S.profil_befehle(tg)
            self.assertIn('/schluessel', tg.geheime_befehle)
            self.assertIn('So:', tg.befehle['/schluessel']('/schluessel'))
            self.assertIn('nichts gespeichert', tg.befehle['/schluessel']('/schluessel gemini kurz'))
            self.assertIn('gespeichert', tg.befehle['/schluessel']('/schluessel Groq gsk_' + 'a' * 30))
            self.assertEqual(gespeichert, {'GROQ_API_KEY': 'gsk_' + 'a' * 30})
            self.assertIn('Luna', tg.befehle['/name']('/name Luna'))
            self.assertIn('/logout', tg.befehle['/profil']('/profil'))
        self.assertEqual(len(neustarts), 2)

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
