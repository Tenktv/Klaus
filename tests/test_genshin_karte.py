"""Kartenregression mit echter Pardis-Karte; sämtliche Eingaben sind gemockt."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
sys.path.insert(0, str(SRC))
import app
import reflexe

BILDER = Path(__file__).resolve().parent / 'genshin_bilder'


def bild(name):
    return np.asarray(Image.open(BILDER / f'{name}.jpg').convert('RGB'))


class KartenErkennung(unittest.TestCase):
    def test_statue_ist_naechstes_freigeschaltetes_ziel(self):
        feld = bild('karte_pardis_statue')
        quest = reflexe.raute(feld, weltkarte=True)
        # Der überlagerte Wegpunkt ist gesperrt; alte Auswahl fand gar nichts.
        self.assertFalse(any(p['offen'] and abs(p['x']-quest[0]) < .02
                             and abs(p['y']-quest[1]) < .04 for p in reflexe.teleportpunkte(feld)))
        ziele = reflexe.teleportziele(feld)
        statue = [p for p in ziele if p['art'] == 'statue' and p['offen']
                  and abs(p['x']-.336) < .015 and abs(p['y']-.235) < .015]
        self.assertEqual(len(statue), 1)

    def test_graue_statue_wird_nicht_freigeschaltet(self):
        feld = bild('karte_pardis_statue').copy()
        region = feld[115:145, 313:334]
        grau = region.min(axis=2)
        region[:] = grau[..., None]
        statuen = [p for p in reflexe.teleportziele(feld) if p['art'] == 'statue'
                   and abs(p['x']-.336) < .015 and abs(p['y']-.235) < .015]
        self.assertTrue(statuen)
        self.assertFalse(statuen[0]['offen'])

    def test_karte_auch_ohne_sichtbare_pins(self):
        original = bild('karte_pardis_statue')
        feld = np.zeros_like(original)
        feld[:60, -80:] = original[:60, -80:]  # Schließen-X
        feld[200:244, 5:43] = original[200:244, 5:43]  # Zoomregler
        self.assertTrue(reflexe.karte_offen(feld))
        feld[200:244, 5:43] = 0
        self.assertFalse(reflexe.karte_offen(feld))  # ein X allein reicht nicht

    def test_dialog_und_domaenenmenue_sind_keine_weltkarte(self):
        for name in ('dialog_hell', 'stadt', 'menue_domaene', 'questbuch_navigate'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.karte_offen(bild(name)))


class KartenEingaben(unittest.TestCase):
    def test_abbruch_beim_ziehen_laesst_maus_los(self):
        instance = object.__new__(app.App)
        instance.stop = threading.Event()
        instance.command = Mock(side_effect=[True, False])  # Fokus weg nach Maustaste-unten
        target = (123, {'left': 0, 'top': 0, 'width': 1920, 'height': 1080})
        with patch.object(app, 'window', return_value=target), \
                patch.object(app.user32, 'SetCursorPos', return_value=1), \
                patch.object(app.win_input, 'mouse') as maus:
            ok = app.App.command(instance, ('karte_ziehen', .3, .5, .7, .5), target)
        self.assertFalse(ok)
        self.assertEqual([c.args[0] for c in maus.call_args_list], [2, 4])

    def test_zoom_stoppt_bei_fokusverlust_vor_rastung(self):
        instance = object.__new__(app.App)
        instance.stop = threading.Event()
        instance.command = Mock(return_value=False)
        target = (123, {'left': 0, 'top': 0, 'width': 1920, 'height': 1080})
        with patch.object(app, 'window', return_value=target), \
                patch.object(app.user32, 'SetCursorPos', return_value=1), \
                patch.object(app.win_input, 'mouse') as maus:
            self.assertFalse(app.App.command(instance, ('karte_zoom', -1), target))
        maus.assert_not_called()


if __name__ == '__main__':
    unittest.main()
