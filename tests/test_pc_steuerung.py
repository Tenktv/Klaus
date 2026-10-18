"""Offline: keine GUI, keine Telegram-Nachrichten, keine Watcher/Prozesse."""
import importlib.util
import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SRC = Path(__file__).resolve().parents[1] / 'src'


def laden(name):
    spec = importlib.util.spec_from_file_location(name, SRC / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SteuerungTests(unittest.TestCase):
    def setUp(self):
        self.dotenv = patch.dict(os.environ, {'PYTHON_DOTENV_DISABLED': '1'})
        self.dotenv.start()
        self.addCleanup(self.dotenv.stop)
        self.modules = patch.dict(sys.modules, {'rechte': types.SimpleNamespace(protokoll=Mock()),
                                              'genshin_modus': types.SimpleNamespace(stoppen=Mock())})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.gate = laden('freigabe')
        self.pc = laden('pc_zugriff')
        self.m = laden('pc_steuerung')
        self.gui = Mock()
        self.gui.size.return_value = (1920, 1080)
        self.gui.position.return_value = (100, 100)
        self.m._gui = Mock(return_value=self.gui)
        self.unicode_impl = self.m._unicode
        self.m._unicode = Mock()
        self.pc._starte_waechter = Mock()
        self.pc._alles_abbrechen = Mock(return_value=0)
        self.pc.melder = Mock()
        self.pc.anzeige = Mock()
        self.gate._log = Mock()
        self.gate.anfragen = Mock(side_effect=self.token)

    def token(self, *args, **kwargs):
        token = 'einmal'
        self.gate._tokens[token] = ('pc_eingabe', time.time())
        return token

    def keine_eingabe(self):
        for name in ('click', 'moveTo', 'scroll', 'press', 'hotkey'):
            getattr(self.gui, name).assert_not_called()
        self.m._unicode.assert_not_called()

    def test_ablehnung_ohne_wirkung(self):
        self.gate.anfragen.return_value = None
        self.gate.anfragen.side_effect = None
        self.assertIn('Nicht freigegeben', self.m.ausfuehren('klicken', x=10, y=20))
        self.keine_eingabe()

    def test_timer_vor_und_nach_freigabe(self):
        self.pc.Z.timer_ende = time.time() - 1
        self.m.ausfuehren('taste', taste='enter')
        self.gate.anfragen.assert_not_called()
        self.pc.Z.timer_ende = None
        def ablauf(*args, **kwargs):
            token = self.token()
            self.pc.Z.timer_ende = time.time() - 1
            return token
        self.gate.anfragen.side_effect = ablauf
        self.m.ausfuehren('taste', taste='enter')
        self.keine_eingabe()

    def test_stop_und_neuer_timer_verwerfen_alte_freigabe(self):
        def stop(*args, **kwargs):
            token = self.token()
            self.pc.stoppen()
            self.pc.Z.gesperrt_bis = 0
            self.pc.timer(None)
            return token
        self.gate.anfragen.side_effect = stop
        self.m.ausfuehren('bewegen', x=10, y=20)
        self.keine_eingabe()

    def test_grenzen_und_ungueltige_werte(self):
        for x, y in ((-1, 0), (1920, 0), (0, 1080), (True, 0), (1.5, 0)):
            self.m.ausfuehren('klicken', x=x, y=y)
        for taste in ('win+r', 'ctrl+alt+delete', 'a', 'keyDown'):
            self.m.ausfuehren('taste', taste=taste)
        self.m.ausfuehren('text', text='echo test\n')
        self.m.ausfuehren('text', text='x'*201)
        self.m.ausfuehren('scrollen', schritte=11)
        self.gui.position.return_value = (-1, 10)
        self.m.ausfuehren('taste', taste='enter')
        self.keine_eingabe()

    def test_jede_aktion_token_overlay_telegram(self):
        self.m.ausfuehren('bewegen', x=10, y=20)
        self.m.ausfuehren('klicken', x=10, y=20)
        self.m.ausfuehren('scrollen', schritte=-2)
        self.m.ausfuehren('taste', taste='enter')
        self.m.ausfuehren('taste', taste='ctrl+a')
        self.assertEqual(self.gate.anfragen.call_count, 5)
        self.assertFalse(self.gate._tokens)
        self.gui.moveTo.assert_called_once_with(10, 20, duration=0)
        self.gui.click.assert_called_once_with(x=10, y=20, button='left')
        self.gui.scroll.assert_called_once_with(-2)
        self.gui.press.assert_called_once_with('enter')
        self.gui.hotkey.assert_called_once_with('ctrl', 'a')
        self.pc.melder.assert_called()
        self.pc.anzeige.assert_called()

    def test_unicode_ohne_clipboard_ohne_textlog(self):
        text = 'Grüße 🌍'
        self.m.ausfuehren('text', text=text)
        self.assertEqual([c.args[0] for c in self.m._unicode.call_args_list], list(text))
        args, kwargs = self.gate.anfragen.call_args
        self.assertNotIn(text, args[1])
        self.assertIn(text, kwargs['an'])  # konkrete, ausschliesslich sichtbare Vorschau
        self.assertNotIn(text, str(self.pc.Z.verlauf))
        self.assertNotIn(text, str(self.pc.anzeige.call_args_list))

    def test_stop_zwischen_unicode_zeichen(self):
        self.m._unicode.side_effect = lambda c: self.pc.stoppen()
        self.m.ausfuehren('text', text='abc')
        self.m._unicode.assert_called_once_with('a')

    def test_live_asynchron_und_einmal_token(self):
        callbacks = []
        self.pc.LIVE.an = True
        def spaeter(art, was, callback, **kwargs):
            callbacks.append(callback)
            return 'Freigabe angefragt'
        self.pc.mit_freigabe = spaeter
        self.assertEqual(self.m.ausfuehren('taste', taste='tab'), 'Freigabe angefragt')
        self.keine_eingabe()
        callbacks[0](self.token())
        callbacks[0]('einmal')
        self.gui.press.assert_called_once_with('tab')

    def test_failsafe_veto(self):
        self.gui.failSafeCheck.side_effect = RuntimeError('Fail-safe')
        self.m.ausfuehren('klicken', x=10, y=20)
        self.keine_eingabe()

    def test_hotkey_fehler_gibt_modifier_frei(self):
        for taste, modifier in (('ctrl+a', 'ctrl'), ('shift+tab', 'shift')):
            with self.subTest(taste=taste):
                self.gui.reset_mock()
                self.gui.FAILSAFE = True
                self.gui.hotkey.side_effect = RuntimeError('Fail-safe nach Modifier down')
                def loslassen(key):
                    self.assertFalse(self.gui.FAILSAFE)
                    self.assertEqual(key, modifier)
                self.gui.keyUp.side_effect = loslassen
                result = self.m.ausfuehren('taste', taste=taste)
                self.assertIn('abgebrochen', result)
                self.gui.keyUp.assert_called_once_with(modifier)
                self.assertIs(self.gui.FAILSAFE, True)
                self.gui.keyDown.assert_not_called()

    def test_hotkey_release_fehler_stellt_failsafe_wieder_her(self):
        for failsafe in (True, False):
            with self.subTest(failsafe=failsafe):
                self.gui.FAILSAFE = failsafe
                self.gui.keyUp.side_effect = RuntimeError('Release fehlgeschlagen')
                with self.assertRaises(RuntimeError):
                    self.m._hotkey(self.gui, 'ctrl+a')
                self.assertIs(self.gui.FAILSAFE, failsafe)

    def test_abgelaufenes_token_ohne_wirkung(self):
        def alt(*args, **kwargs):
            token = self.token()
            self.gate._tokens[token] = ('pc_eingabe', time.time() - 121)
            return token
        self.gate.anfragen.side_effect = alt
        self.m.ausfuehren('taste', taste='enter')
        self.keine_eingabe()

    def test_zeitablauf_und_wiedereroeffnung_veto(self):
        def ablauf(*args, **kwargs):
            token = self.token()
            self.pc._zeit_ablaufen()
            self.pc.timer(None)
            return token
        self.gate.anfragen.side_effect = ablauf
        self.m.ausfuehren('text', text='Hallo')
        self.keine_eingabe()

    def test_abgelaufener_timer_vor_waechter_tick_verwirft_eingabe(self):
        for neues_limit in (None, 15):
            with self.subTest(neues_limit=neues_limit):
                self.pc.Z.timer_ende = None
                self.pc.Z.zeit_abgelaufen = False
                def neu(*args, **kwargs):
                    token = self.token()
                    self.pc.Z.timer_ende = time.time() - 1
                    self.pc.timer(neues_limit)
                    return token
                self.gate.anfragen.side_effect = neu
                self.m.ausfuehren('text', text='Hallo')
                self.keine_eingabe()
                self.pc._alles_abbrechen.assert_called()

    def test_alter_waechter_tick_stoppt_keinen_neuen_timer(self):
        alte_frist = time.time() - 1
        self.pc.Z.timer_ende = alte_frist
        self.pc.timer(15)
        neue_frist = self.pc.Z.timer_ende
        generation = self.pc.Z.abbruch_generation
        self.pc._alles_abbrechen.reset_mock()
        self.pc._zeit_ablaufen(alte_frist)
        self.assertEqual(self.pc.Z.timer_ende, neue_frist)
        self.assertEqual(self.pc.Z.abbruch_generation, generation)
        self.pc._alles_abbrechen.assert_not_called()

    def test_windows_unicode_ereignisse_ohne_gui(self):
        events = []
        def send(count, inputs, size):
            events.extend((e.type, e.payload.keyboard.scan, e.payload.keyboard.flags) for e in inputs)
            # INPUT ist auf Windows 64-bit 40 Bytes, auf 32-bit 28 Bytes.
            self.assertEqual(size, 40 if self.m.ctypes.sizeof(self.m.ctypes.c_void_p) == 8 else 28)
            return count
        dll = Mock()
        dll.SendInput.side_effect = send
        with patch.object(self.m.ctypes, 'WinDLL', return_value=dll, create=True):
            self.unicode_impl('🌍')
        self.assertEqual(events, [(1, 0xD83C, 4), (1, 0xD83C, 6),
                                  (1, 0xDF0D, 4), (1, 0xDF0D, 6)])


if __name__ == '__main__':
    unittest.main()
