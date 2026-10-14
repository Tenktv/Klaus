import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
with patch('dotenv.load_dotenv', return_value=False):
    import betrieb
    import ki_kosten as k
    import ersatz_ki
    import protokoll
    import assistent
    import gemini_live
    import instanz


class StabilitaetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch = patch.object(betrieb, 'DATEI', Path(self.tmp.name) / 'betrieb.json')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        betrieb._cache.update(zeit=0, ruhe=False)

    def test_ruhe_persistiert_und_beschaedigte_datei_still(self):
        betrieb.setze_ruhe(True)
        betrieb._cache['zeit'] = 0
        self.assertTrue(betrieb.ruhe())
        betrieb.DATEI.write_text('kaputt')
        betrieb._cache['zeit'] = 0
        self.assertTrue(betrieb.ruhe())
        betrieb.setze_ruhe(False)
        self.assertFalse(betrieb.ruhe())

    def test_sprachausgabe_zentral_gefiltert(self):
        a = SimpleNamespace(ist_stumm=True, b=SimpleNamespace(nachricht=Mock(), pegel=Mock(), zustand=Mock()),
                            sprech_sperre=threading.Lock(), per_telegram=lambda: False, log=Mock(), zeige=Mock())
        a.darf_sprechen = lambda quelle: assistent.Assistent.darf_sprechen(a, quelle)
        with patch.object(assistent.voice, 'sprich') as sprechen:
            assistent.Assistent.sage(a, 'Hallo')
            sprechen.assert_not_called()
            a.ist_stumm = False
            assistent.Assistent.sage(a, 'Erinnerung', quelle='kalender')
            sprechen.assert_not_called()
            betrieb.setze_ruhe(True)
            assistent.Assistent.sage(a, 'Coach', quelle='coach')
            sprechen.assert_not_called()
            betrieb.setze_ruhe(False)
            assistent.Assistent.sage(a, 'Antwort')
            sprechen.assert_called_once()
            self.assertFalse(sprechen.call_args.kwargs['abbruch']())
            betrieb.setze_ruhe(True)
            self.assertTrue(sprechen.call_args.kwargs['abbruch']())

    def test_gemini_ruhe_verwirft_audio(self):
        aus = Mock()
        stream = Mock()
        stream.__enter__ = Mock(return_value=aus)
        stream.__exit__ = Mock(return_value=False)
        a = SimpleNamespace(wiedergabe=queue.Queue(), a=SimpleNamespace(darf_sprechen=lambda quelle: False))
        a.wiedergabe.put(b'\x00\x00')
        a.wiedergabe.put(None)
        with patch.dict(sys.modules, {'sounddevice': SimpleNamespace(RawOutputStream=lambda **kwargs: stream)}):
            gemini_live.GeminiGespraech._abspielen(a)
        aus.write.assert_not_called()

    def test_lokale_stimme_bricht_laufende_wiedergabe_ab(self):
        import numpy as np
        import stimme
        sd = SimpleNamespace(play=Mock(), stop=Mock(), wait=Mock())
        abbruch = Mock(side_effect=[False, False, True])
        with patch.dict(sys.modules, {'sounddevice': sd}), patch.object(stimme, 'saetze', return_value=[(np.zeros(16000), 16000)]), patch('time.sleep'), patch.object(betrieb, 'ruhe', return_value=False):
            with self.assertRaises(InterruptedError):
                stimme.sprich('test', 'Test', abbruch=abbruch)
        sd.stop.assert_called_once()
        sd.wait.assert_not_called()

    def test_windows_fallback_bleibt_ohne_tts(self):
        engine = Mock()
        with patch.object(assistent.voice.stimme, 'sprich', side_effect=RuntimeError('offline')), patch.object(assistent.voice.stimme, 'name', return_value='test'), patch.dict(sys.modules, {'pyttsx3': engine}), patch.object(betrieb, 'ruhe', return_value=False):
            assistent.voice.sprich('Test', False)
        engine.init.assert_not_called()

    def test_gemini_lange_audiostuecke_bleiben_abbrechbar(self):
        aus = Mock()
        stream = Mock()
        stream.__enter__ = Mock(return_value=aus)
        stream.__exit__ = Mock(return_value=False)
        a = SimpleNamespace(wiedergabe=queue.Queue(), a=SimpleNamespace(darf_sprechen=Mock(side_effect=[True, True, False]), b=SimpleNamespace(pegel=Mock())))
        a.wiedergabe.put(b'\x00\x00' * gemini_live.LAUTSPRECHER_RATE)
        a.wiedergabe.put(None)
        with patch.dict(sys.modules, {'sounddevice': SimpleNamespace(RawOutputStream=lambda **kwargs: stream)}):
            gemini_live.GeminiGespraech._abspielen(a)
        aus.write.assert_called_once()
        self.assertEqual(len(aus.write.call_args.args[0]), gemini_live.LAUTSPRECHER_RATE // 10 * 2)

    def test_instanz_sperre_akzeptiert_keine_zweite(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 123
        with patch.object(instanz, '_handle', None), patch.object(instanz.ctypes, 'WinDLL', return_value=kernel), patch.object(instanz.ctypes, 'get_last_error', return_value=183):
            self.assertFalse(instanz.sperren())
            kernel.CloseHandle.assert_called_once_with(123)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows-Named-Mutex')
    def test_echter_zweiter_prozess_ohne_audio_abgelehnt(self):
        import subprocess
        if not instanz.sperren():
            self.skipTest('Eine echte Klaus-Instanz haelt die Sperre bereits.')
        result = subprocess.run([sys.executable, '-c', 'import instanz; print(instanz.sperren())'],
                                cwd=Path(instanz.__file__).parent, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'False')

    def test_protokoll_gesundheit_und_atomisches_speichern(self):
        p = protokoll.Protokoll('Test', None)
        p._strom = object()
        p._faden = SimpleNamespace(is_alive=lambda: True)
        with patch.object(protokoll.time, 'monotonic', return_value=1000):
            p._letztes_audio = p._worker_tick = 1000
            p._letzter_text = 399
            self.assertIn('zehn Minuten', p.gesundheit()['grund'])
            p._letzter_text = 1000
            self.assertFalse(p.gesundheit()['warnung'])
            p._letztes_audio = 960
            self.assertIn('Audiodaten', p.gesundheit()['grund'])
            p._letztes_audio = 1000
            p._worker_tick = 870
            self.assertIn('Spracherkennung', p.gesundheit()['grund'])
        p.datei = Path(self.tmp.name) / 'meeting.md'
        p.saetze = [(1, 'Hallo Seminar')]
        p._sichern()
        self.assertIn('Hallo Seminar', p.datei.read_text(encoding='utf-8'))
        self.assertFalse(p.datei.with_suffix('.md.tmp').exists())

    def test_warnungen_dedupliziert(self):
        p = protokoll.Protokoll('Test', None, warnung=Mock())
        p._halt = Mock()
        p._halt.wait.side_effect = [False, False, False, True]
        p.gesundheit = Mock(side_effect=[{'grund': 'Kein Text'}, {'grund': 'Kein Text'}, {'grund': ''}])
        p._waechter()
        self.assertEqual(p.warnung.call_count, 2)


class KostenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, filename in [('KONFIG', 'ki.json'), ('DB', 'kosten.sqlite')]:
            p = patch.object(k, name, Path(self.tmp.name) / filename)
            p.start()
            self.addCleanup(p.stop)
        self.config = {'aktiv': True, 'tageslimit_usd': 1, 'monatslimit_usd': 2,
                       'modelle': [{'anbieter': 'openrouter1', 'modell': 'premium-test',
                                    'eingabe_usd_million': 10, 'ausgabe_usd_million': 100, 'max_ausgabe_tokens': 512}]}
        self.speichern()

    def speichern(self):
        k.KONFIG.write_text(json.dumps(self.config), encoding='utf-8')

    def buchen(self):
        return k.reservieren('openrouter1', 'premium-test', [{'role': 'user', 'content': 'Hallo'}])

    def test_opt_in_modell_und_bild_sperre(self):
        self.config['aktiv'] = False
        self.speichern()
        with self.assertRaises(k.BudgetFehler): self.buchen()
        self.config['aktiv'] = True
        self.speichern()
        with self.assertRaises(k.BudgetFehler): k.reservieren('openrouter1', 'nicht-freigegeben', [])
        with self.assertRaises(k.BudgetFehler): k.reservieren('openrouter1', 'premium-test', [], bild=True)

    def test_reservieren_abrechnen_und_fehlende_nutzung(self):
        t = self.buchen()
        vorher = k.status()['tag_usd']
        self.assertGreater(vorher, 0)
        k.abrechnen(t, None)
        self.assertEqual(k.status()['tag_usd'], vorher)
        k.abrechnen(t, {'cost': .004})
        self.assertEqual(k.status()['tag_usd'], .004)
        self.assertEqual(k.status()['tag_reserviert'], 0)
        k.abrechnen(t, {'cost': 100})
        self.assertEqual(k.status()['tag_usd'], .004)

    def test_parallele_reservierungen_ueberschreiten_limit_nicht(self):
        from concurrent.futures import ThreadPoolExecutor
        self.config['tageslimit_usd'] = .07
        self.speichern()
        def versuch(_):
            try: self.buchen(); return True
            except k.BudgetFehler: return False
        with ThreadPoolExecutor(max_workers=6) as pool:
            ergebnisse = list(pool.map(versuch, range(6)))
        self.assertEqual(sum(ergebnisse), 1)
        self.assertLessEqual(k.status()['tag_usd'], .07)

    def test_deaktiviert_keine_http_anfrage(self):
        self.config['aktiv'] = False
        self.speichern()
        a = ersatz_ki.Anbieter('openrouter1', 'https://example.invalid', 'test', [], [], feste_modelle=['premium-test'])
        with patch.object(ersatz_ki, 'ANBIETER', [a]), patch.object(ersatz_ki.requests, 'post') as post:
            with self.assertRaises(ersatz_ki.ErsatzFehler): ersatz_ki.chat([{'role': 'user', 'content': 'Test'}])
            post.assert_not_called()

    def test_monatslimit_und_ungueltige_preise(self):
        self.config['monatslimit_usd'] = .001
        self.speichern()
        with self.assertRaises(k.BudgetFehler): self.buchen()
        self.config['monatslimit_usd'] = 10
        for preis in (None, -1, 'NaN'):
            self.config['modelle'][0]['eingabe_usd_million'] = preis
            self.speichern()
            with self.assertRaises(k.BudgetFehler): self.buchen()

    def test_api_tokenlimit_und_kosten_erfasst(self):
        a = ersatz_ki.Anbieter('openrouter1', 'https://example.invalid', 'test', [], [], feste_modelle=['premium-test'])
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'message': {'content': 'Antwort'}}], 'usage': {'cost': .001}}
        with patch.object(ersatz_ki, 'ANBIETER', [a]), patch.object(ersatz_ki.requests, 'post', return_value=response) as post:
            self.assertEqual(ersatz_ki.chat([{'role': 'user', 'content': 'Test'}])['message']['content'], 'Antwort')
            self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 512)
        self.assertEqual(k.status()['tag_usd'], .001)


if __name__ == '__main__':
    unittest.main()
