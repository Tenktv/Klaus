"""Regressionen ohne Screenshots, API-Aufrufe oder echte Eingaben."""
import ctypes
import json
from pathlib import Path
import queue
import sys
import unittest
from unittest.mock import Mock, patch, call

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC / 'genshin_agent'))
sys.path.insert(0, str(SRC))
import core
import win_input
import app
import genshin_modus


class Decisions(unittest.TestCase):
    def decision(self, **changes):
        value = dict(scene='exploration', state='City', reason='Walk',
                     enemy_visible=False, action={'type': 'key', 'key': 'w', 'seconds': 0.5})
        value.update(changes)
        return core.parse_decision(json.dumps(value))

    def test_missing_action_becomes_controlled_error(self):
        with self.assertRaises(core.InvalidDecision):
            self.decision(action=None)

    def test_truncated_json_becomes_controlled_error(self):
        with self.assertRaises(core.InvalidDecision):
            core.parse_decision('{"state":')

    def test_party_sidebar_cannot_justify_attack(self):
        result = self.decision(action={'type': 'click', 'x': 0.5, 'y': 0.5})
        self.assertEqual(result['action']['type'], 'wait')

    def test_menu_discards_key(self):
        self.assertEqual(self.decision(scene='menu')['action']['type'], 'stop')
        self.assertEqual(self.decision(scene='menu', action={'type': 'key', 'key': 'e'})['action']['type'], 'stop')

    def test_real_combat_allows_attack(self):
        result = self.decision(scene='combat', enemy_visible=True, action={'type': 'key', 'key': 'e'})
        self.assertEqual(result['action']['key'], 'e')

    def test_nonfinite_number_rejected(self):
        for value in (float('nan'), float('inf'), True, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                core.validate_action({'type': 'key', 'key': 'w', 'seconds': value})


class WindowsInput(unittest.TestCase):
    def test_scancode_and_release(self):
        captured = []
        with patch.object(win_input, '_send', side_effect=lambda e: captured.append((e.payload.keyboard.scan, e.payload.keyboard.flags))):
            win_input.key(0x57)
            win_input.key(0x57, up=True)
        self.assertEqual(captured, [(0x11, 8), (0x11, 10)])
        self.assertEqual(ctypes.sizeof(win_input.Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_uipi_blocks_before_input(self):
        with patch.object(win_input, 'permission_status', return_value={'blocked_by_uipi': True}):
            with self.assertRaisesRegex(PermissionError, 'UIPI'):
                win_input.ensure_permissions(123)

    def test_rejected_sendinput_is_not_reported_as_success(self):
        with patch.object(win_input.u, 'SendInput', return_value=0):
            with self.assertRaises(OSError):
                win_input.mouse(2)


class Controller(unittest.TestCase):
    def instance(self):
        instance = object.__new__(app.App)
        instance.stop = Mock()
        instance.stop.is_set.return_value = False
        instance.stop.wait.return_value = False
        instance.messages = queue.Queue()
        instance.running = True
        instance.stop_reason = ''
        return instance

    def test_focus_change_discards_action(self):
        instance = self.instance()
        with patch.object(app, 'window', return_value=None), patch.object(win_input, 'key') as key:
            self.assertFalse(instance.execute({'type': 'key', 'key': 'w', 'seconds': 0.1}, (10, {})))
            key.assert_not_called()

    def test_held_key_released_when_focus_is_lost(self):
        instance = self.instance()
        target = (10, {})
        with patch.object(app, 'window', side_effect=[target, None]), \
                patch.object(win_input, 'ensure_permissions'), patch.object(win_input, 'key') as key:
            instance.execute({'type': 'key', 'key': 'w', 'seconds': 1}, target)
            self.assertEqual(key.call_args_list, [call(0x57), call(0x57, up=True)])
            instance.stop.set.assert_called()

    def test_same_title_in_other_process_is_rejected(self):
        with patch.object(app, 'foreground_identity', return_value=(123, 'Genshin Impact', 'msedge.exe')):
            self.assertIsNone(app.window())

    def test_three_bad_answers_stop_without_input(self):
        instance = self.instance()
        instance.wait_for_game = Mock(return_value=(1, {}))
        shot = Mock(size=(1, 1), rgb=b'\0\0\0')
        screen = Mock()
        screen.grab.return_value = shot
        context = Mock()
        context.__enter__ = Mock(return_value=screen)
        context.__exit__ = Mock(return_value=False)
        with patch.object(app.mss, 'mss', return_value=context), \
                patch.object(app, 'decide', side_effect=core.InvalidDecision('action fehlt')) as decide, \
                patch.object(instance, 'execute') as execute:
            instance.run('', 'gemma3:4b', 'test', True, 'local')
            self.assertEqual(decide.call_count, 3)
            execute.assert_not_called()
        self.assertFalse(instance.running)
        self.assertTrue(any('Drei ungültige' in item for item in instance.messages.queue))


class KlausBridge(unittest.TestCase):
    def test_stop_touches_only_session_marker(self):
        folder = Mock()
        with patch.object(genshin_modus, 'ORDNER', folder):
            folder.__truediv__ = Mock(return_value=Mock())
            self.assertIn('Stopp', genshin_modus.stoppen())
            folder.__truediv__.assert_called_once_with('stop.request')
            folder.__truediv__.return_value.touch.assert_called_once_with()

    def test_unknown_action_never_launches_process(self):
        with patch.object(genshin_modus.subprocess, 'Popen') as launch:
            self.assertIn('Erlaubt', genshin_modus.werkzeug('run_shell'))
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
