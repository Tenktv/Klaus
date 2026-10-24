"""Claude-Brücke und Rätsel-Werkzeuge: keine echten Eingaben, Dateien nur im Temp-Ordner."""
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC / 'genshin_agent'))
import app
import bruecke_cli
import fertigkeiten as f
import reflexe

TEAM = f.team_lesen('1=anemo 2=pyro 3=hydro 4=cryo 5=pyro')


class Werkzeuge(unittest.TestCase):
    def test_team_lesen(self):
        self.assertEqual(TEAM, {1: 'anemo', 2: 'pyro', 3: 'hydro', 4: 'cryo', 5: 'pyro'})
        self.assertEqual(f.team_lesen('1=pyro 9=hydro x=geo 2=quatsch'), {1: 'pyro'})

    def test_drehen_nutzt_gelernte_lenkung(self):
        self.assertEqual(f.uebersetzen({'tun': 'drehen', 'grad': 45}, 6, TEAM)[0], ('blick', 270, 0))

    def test_zielen_bildrand(self):
        dx = f.uebersetzen({'tun': 'zielen', 'x': 1.0, 'y': 0.5}, 10, TEAM)[0][1]
        self.assertEqual(dx, round(reflexe.HFOV / 2 * 10))

    def test_angreifen_wechselt_auf_element(self):
        befehle = f.uebersetzen({'tun': 'angreifen', 'element': 'pyro', 'art': 'e'}, 6, TEAM)
        self.assertEqual(befehle[0], ('tippen', '2', 0.08))
        self.assertIn(('tippen', 'e', 0.08), befehle)

    def test_element_fehlt_im_team(self):
        with self.assertRaisesRegex(f.Ungueltig, 'electro'):
            f.uebersetzen({'tun': 'angreifen', 'element': 'electro'}, 6, TEAM)

    def test_gleiten_laesst_w_wieder_los(self):
        befehle = f.uebersetzen({'tun': 'gleiten', 'sekunden': 2}, 6, TEAM)
        self.assertEqual((befehle[0], befehle[-1]), (('halten', 'w'), ('loslassen', 'w')))

    def test_grenzen(self):
        for befehl in ({'tun': 'taste', 'taste': 'enter'}, {'tun': 'laufen', 'sekunden': 60},
                       {'tun': 'drehen', 'grad': float('nan')}, {'tun': 'figur', 'slot': 7},
                       {'tun': 'zielen', 'x': 1.5}, {'tun': 'shell'}, {'tun': 'warten', 'sekunden': True}):
            with self.subTest(befehl=befehl), self.assertRaises(f.Ungueltig):
                f.uebersetzen(befehl, 6, TEAM)

    def test_ganze_sendung_oder_nichts(self):
        with self.assertRaises(f.Ungueltig):
            f.pruefen([{'tun': 'interagieren'}, {'tun': 'taste', 'taste': 'enter'}], 6, TEAM)
        with self.assertRaises(f.Ungueltig):
            f.pruefen([{'tun': 'springen'}] * 9, 6, TEAM)


class Bruecke(unittest.TestCase):
    def setUp(self):
        self.ordner = Path(tempfile.mkdtemp())
        self.patch = patch.object(app, 'BRUECKE', self.ordner)
        self.patch.start()
        self.instance = object.__new__(app.App)
        self.instance.stop = threading.Event()
        self.instance.messages = queue.Queue()
        self.instance.team = TEAM
        self.pilot = reflexe.Pilot(600)
        self.state = {'nr': 0, 'bild_nach_nr': 0, 'ergebnis': None, 'frisch_ab': 0.0, 'geschrieben': 0.0}

    def tearDown(self):
        self.patch.stop()

    def befehl(self, nr, befehle, alter=0):
        pfad = self.ordner / f'befehl_{nr}.json'
        pfad.write_text(json.dumps({'befehle': befehle}), encoding='utf-8')
        if alter:
            os.utime(pfad, (time.time() - alter, time.time() - alter))

    def test_fuehrt_aus_und_meldet_mit_frischem_bild(self):
        self.befehl(1, [{'tun': 'interagieren'}])
        info = {'hud': True, 'ziel': None, 'kegel': 10.0, 'dialog': False, 'laden': False, 'gegner': None, 'bewegt': True}
        voll = np.zeros((1080, 1920, 3), np.uint8)
        with patch.object(self.instance, 'command', return_value=True) as command:
            self.instance.bridge_step(voll, info, (1, {}), self.pilot, self.state)
            command.assert_any_call(('tippen', 'f', 0.08), (1, {}))
        self.assertFalse((self.ordner / 'zustand.json').exists())  # erst nach der Wirkung
        self.state['frisch_ab'] = 0
        self.instance.bridge_step(voll, info, (1, {}), self.pilot, self.state)
        zustand = json.loads((self.ordner / 'zustand.json').read_text(encoding='utf-8'))
        self.assertEqual((zustand['nr'], zustand['bild_nach_nr'], zustand['ergebnis']['ok']), (1, 1, True))
        self.assertTrue((self.ordner / 'bild.jpg').exists())
        self.assertFalse(list(self.ordner.glob('befehl_*.json')))

    def test_fokusverlust_bricht_ab_und_laesst_tasten_los(self):
        befehle = []

        def command(order, target):
            befehle.append(order)
            return order[0] != 'warten'  # erstes Warten scheitert = Fokus weg

        with patch.object(self.instance, 'command', side_effect=command):
            ergebnis = self.instance.bridge_execute({'befehle': [{'tun': 'gleiten', 'sekunden': 2}]}, (1, {}), self.pilot)
        self.assertFalse(ergebnis['ok'])
        self.assertEqual(befehle[-1], ('loslassen', 'w'))

    def test_ungueltiger_befehl_fuehrt_nichts_aus(self):
        with patch.object(self.instance, 'command') as command:
            ergebnis = self.instance.bridge_execute({'befehle': [{'tun': 'taste', 'taste': 'enter'}]}, (1, {}), self.pilot)
        self.assertFalse(ergebnis['ok'])
        command.assert_not_called()

    def test_alte_und_doppelte_befehle_werden_verworfen(self):
        self.state['nr'] = 5
        self.befehl(4, [{'tun': 'springen'}])
        self.befehl(7, [{'tun': 'springen'}], alter=120)
        self.befehl(6, [{'tun': 'interagieren'}])
        gefunden = self.instance.bridge_take(self.state)
        self.assertEqual([nr for nr, _ in gefunden], [6])
        self.assertFalse(list(self.ordner.glob('befehl_*.json')))

    def test_cli_wartet_auf_ergebnis(self):
        def panel():
            for _ in range(50):
                if (self.ordner / 'befehl_1.json').exists():
                    break
                time.sleep(0.05)
            (self.ordner / 'befehl_1.json').unlink()
            (self.ordner / 'zustand.json').write_text(json.dumps(
                {'nr': 1, 'bild_nach_nr': 1, 'zeit': time.time(), 'spiel_aktiv': True, 'ergebnis': {'ok': True}}),
                encoding='utf-8')

        thread = threading.Thread(target=panel)
        thread.start()
        with patch.object(bruecke_cli, 'ORDNER', self.ordner), patch('builtins.print'):
            self.assertEqual(bruecke_cli.senden({'tun': 'interagieren'}, wartezeit=5), 0)
        thread.join()

    def test_cli_raeumt_bei_zeitueberschreitung_auf(self):
        with patch.object(bruecke_cli, 'ORDNER', self.ordner), patch('builtins.print'):
            self.assertEqual(bruecke_cli.senden([{'tun': 'springen'}], wartezeit=0.5), 2)
        self.assertFalse(list(self.ordner.glob('befehl_*.json')))


class Hauptschleife(unittest.TestCase):
    def test_autopilot_im_claude_modus(self):
        """F11-Modus: eigener Pilot ruht, Claudes Befehl wird ausgeführt, Zustand mit Bild danach."""
        ordner = Path(tempfile.mkdtemp())
        (ordner / 'befehl_1.json').write_text(json.dumps({'befehle': [{'tun': 'interagieren'}]}), encoding='utf-8')
        instance = object.__new__(app.App)
        instance.stop = threading.Event()
        instance.messages = queue.Queue()
        instance.running = True
        instance.stop_reason = ''
        instance.bridge_active = True
        instance.team = TEAM
        feld = np.zeros((540, 960, 3), np.uint8)
        shot = Mock(width=960, height=540, rgb=feld.tobytes())
        screen = Mock()
        screen.grab.return_value = shot
        context = Mock(__enter__=Mock(return_value=screen), __exit__=Mock(return_value=False))
        befehle = []

        def merken(order, target):
            befehle.append(order)
            return True

        def warten(sekunden=None):
            zustand = ordner / 'zustand.json'
            if zustand.exists() and json.loads(zustand.read_text(encoding='utf-8')).get('bild_nach_nr') == 1:
                instance.stop.set()
            return threading.Event.wait(instance.stop, min(sekunden or 0, 0.01))

        with patch.object(app, 'BRUECKE', ordner), patch.object(app.mss, 'mss', return_value=context), \
                patch.object(app, 'window', return_value=(1, {})), \
                patch.object(app.win_input, 'ensure_permissions'), \
                patch.object(app, 'ki_hinweis') as ki, \
                patch.object(instance, 'save_diag'), \
                patch.object(instance, 'command', side_effect=merken), \
                patch.object(instance.stop, 'wait', side_effect=warten):
            # Befehlsdatei entsteht erst nach dem Start (alte Dateien werden beim Start verworfen).
            (ordner / 'befehl_1.json').unlink()
            threading.Timer(0.2, lambda: (ordner / 'befehl_1.json').write_text(
                json.dumps({'befehle': [{'tun': 'interagieren'}]}), encoding='utf-8')).start()
            instance.autopilot('gemma3:4b', 'test', False, 'gold', 600)
            ki.assert_not_called()
        self.assertIn(('tippen', 'f', 0.08), befehle)
        self.assertNotIn(('halten', 'w'), befehle)  # eigener Pilot lief nicht
        zustand = json.loads((ordner / 'zustand.json').read_text(encoding='utf-8'))
        self.assertTrue(zustand['ergebnis']['ok'])


class Teleport(unittest.TestCase):
    """Ablauf mit echten Bildern als „Bildschirm“: jede Eingabe schaltet zum nächsten Bild."""

    def setUp(self):
        from PIL import Image
        bilder = Path(__file__).resolve().parent / 'genshin_bilder'
        self.bild = lambda name: np.asarray(Image.open(bilder / f'{name}.jpg').convert('RGB'))
        self.instance = object.__new__(app.App)
        self.instance.stop = threading.Event()
        self.instance.messages = queue.Queue()
        self.instance.save_diag = Mock()  # Tests dürfen keine Laufzeitdiagnosen überschreiben.
        self.befehle = []

    def ablauf(self, folge):
        """folge: Bild nach jeder Eingabe (Tasten/Klicks); Warten ändert nichts."""
        zustand = {'i': 0}

        def command(order, target):
            self.befehle.append(order)
            if order[0] in ('tippen', 'maus_klick'):
                zustand['i'] = min(zustand['i'] + 1, len(folge) - 1)
            return True
        look = lambda: self.bild(folge[zustand['i']])
        with patch.object(self.instance, 'command', side_effect=command):
            return self.instance.teleport(look, (1, {}))

    def test_karte_auswahlliste_teleport(self):
        # M → Karte (Questsymbol in der Mitte) → Klick auf nächsten freien Teleportpunkt →
        # Auswahlliste → Klick auf den neuen Pin („Teleport Waypoint“) → Teleport-Fenster → F.
        ok = self.ablauf(['stadt', 'karte', 'karte_auswahlliste', 'karte_teleport_fenster', 'karte_teleport_fenster'])
        self.assertTrue(ok)
        tasten = [b for b in self.befehle if b[0] in ('tippen', 'maus_klick')]
        self.assertEqual(tasten[0], ('tippen', 'm', 0.08))
        klicks = [b for b in tasten if b[0] == 'maus_klick']
        self.assertEqual(len(klicks), 2)
        self.assertAlmostEqual(klicks[0][1], 0.564, delta=0.02)  # Teleportpunkt nah am Questsymbol
        self.assertAlmostEqual(klicks[1][1], 0.676, delta=0.02)  # „Teleport Waypoint“ in der Liste
        self.assertEqual(tasten[-1], ('tippen', 'f', 0.08))      # F = Teleport

    def test_wueste_waehlt_naehere_freie_statue(self):
        # Dar al-Shifa: seit 0.12 zählt auch die freie Statue nordwestlich als
        # Ziel. Sie liegt näher als der bisher gewählte Wegpunkt südwestlich.
        ok = self.ablauf(['stadt', 'karte_m_wueste', 'karte_m_teleport_fenster', 'karte_m_teleport_fenster'])
        self.assertTrue(ok)
        klick = [b for b in self.befehle if b[0] == 'maus_klick'][0]
        self.assertAlmostEqual(klick[1], 0.468, delta=0.015)
        self.assertAlmostEqual(klick[2], 0.661, delta=0.015)
        self.assertEqual([b for b in self.befehle if b[0] == 'tippen'][-1], ('tippen', 'f', 0.08))

    def test_karte_geht_nicht_auf_dann_esc(self):
        ok = self.ablauf(['stadt', 'questbuch_navigate', 'questbuch_navigate', 'stadt'])
        self.assertFalse(ok)
        self.assertIn(('tippen', 'escape', 0.08), self.befehle)
        self.assertNotIn('maus_klick', [b[0] for b in self.befehle])

    def test_ohne_teleport_knopf_kein_f_auf_der_karte(self):
        # Klick führt nur zum Questfenster („Cancel Navigation“): kein F, sonst Navigation weg.
        ok = self.ablauf(['stadt', 'karte', 'karte_quest_fenster', 'karte', 'karte_quest_fenster',
                          'karte', 'karte_quest_fenster', 'karte', 'stadt'])
        self.assertFalse(ok)
        nach_karte = self.befehle[[i for i, b in enumerate(self.befehle) if b[0] == 'maus_klick'][0]:]
        self.assertNotIn(('tippen', 'f', 0.08), nach_karte)


class Mitlesen(unittest.TestCase):
    def setUp(self):
        self.instance = object.__new__(app.App)
        self.instance.messages = queue.Queue()
        self.instance.reset_dialog_state()
        self.state = {'sig': None, 'since': 0.0, 'stable': 0}
        bilder = Path(__file__).resolve().parent / 'genshin_bilder'
        from PIL import Image
        self.dialog = np.asarray(Image.open(bilder / 'dialog_hell.jpg').convert('RGB'))

    def schritt(self, now, feld=None):
        info = {'dialog': True}
        feld = self.dialog if feld is None else feld
        self.instance.track_dialog(info, feld, feld, self.state, now, reading=True)
        return info['dialog_bereit']

    def test_wartet_nie_auf_gemma(self):
        # Früher: Dialog blieb stehen, bis Gemma (10-20 s pro Zeile) vorgelesen hatte.
        self.assertTrue(all(self.schritt(t * 0.1) for t in range(10)))
        self.assertEqual(len(self.instance.dialog_jobs), 1)  # Zeile zum Vorlesen vorgemerkt

    def test_gleiche_zeile_nur_einmal(self):
        for t in range(30):
            self.schritt(t * 0.1)
        self.assertEqual(len(self.instance.dialog_jobs), 1)

    def test_bewegter_hintergrund_ist_keine_neue_zeile(self):
        for t in range(5):
            self.schritt(t * 0.1)
        hintergrund = self.dialog.copy()
        hintergrund[:400] = np.roll(hintergrund[:400], 37, axis=1)  # Szene bewegt sich, Text bleibt
        for t in range(5, 12):
            self.schritt(t * 0.1, hintergrund)
        self.assertEqual(len(self.instance.dialog_jobs), 1)

    def test_neue_zeile_wird_vorgemerkt(self):
        for t in range(5):
            self.schritt(t * 0.1)
        from PIL import Image
        andere = np.asarray(Image.open(Path(__file__).resolve().parent / 'genshin_bilder' / 'dialog_luke.jpg').convert('RGB'))
        anders = self.dialog.copy()
        anders[430:505] = andere[430:505]  # echte andere Dialogzeile
        for t in range(5, 12):
            self.schritt(t * 0.1, anders)
        self.assertEqual(len(self.instance.dialog_jobs), 2)

    def test_zeile_protokolliert_mit_stichwort(self):
        ordner = Path(tempfile.mkdtemp())
        with patch.object(app, 'LOGS', ordner):
            self.instance.record_line({'sprecher': 'Paimon', 'text': 'Green symbolizes  Dendro, ignite it with Pyro!'})
            self.instance.record_line({'sprecher': 'Paimon', 'text': 'Green symbolizes Dendro, ignite it with Pyro!'})
        zeilen = (ordner / 'dialoge.txt').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(zeilen), 1)  # doppelte Zeile nur einmal
        self.assertIn('Paimon: Green symbolizes Dendro', zeilen[0])
        self.assertEqual({w for _, w in self.instance.keywords}, {'dendro', 'pyro'})

    def test_ohne_ki_nie_warten(self):
        info = {'dialog': True}
        self.instance.track_dialog(info, self.dialog, self.dialog, self.state, 0.0, reading=False)
        self.assertTrue(info['dialog_bereit'])


class Befehlsausfuehrung(unittest.TestCase):
    def test_warten_bricht_bei_fokusverlust_ab(self):
        instance = object.__new__(app.App)
        instance.stop = threading.Event()
        with patch.object(app, 'window', return_value=None):
            self.assertFalse(instance.command(('warten', 1.0), (1, {})))

    def test_maus_halten_laesst_immer_los(self):
        instance = object.__new__(app.App)
        instance.stop = Mock()
        instance.stop.is_set.return_value = False
        instance.stop.wait.side_effect = RuntimeError('abbruch')
        with patch.object(app, 'window', return_value=(1, {})), patch.object(app.win_input, 'mouse') as maus:
            with self.assertRaises(RuntimeError):
                instance.command(('maus_halten', 1.0), (1, {}))
        self.assertEqual([c.args[0] for c in maus.call_args_list], [2, 4])


if __name__ == '__main__':
    unittest.main()
