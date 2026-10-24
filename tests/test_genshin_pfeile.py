"""Regression: rosa Begleiter ist kein Gegnerpfeil, auch bei anderer Rasterlage.

Gespeicherte Spielbilder, keine Eingaben oder Bildschirmaufnahmen. Das Begleiterbild
stammt aus logs/diag/202144.jpg; UID unten rechts ist geschwärzt.
"""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
sys.path.insert(0, str(SRC))
import reflexe


def bild(name):
    with Image.open(Path(__file__).resolve().parent / 'genshin_bilder' / f'{name}.jpg') as picture:
        return np.asarray(picture.convert('RGB'))


class GegnerpfeilKontur(unittest.TestCase):
    def test_begleiter_auch_bei_anderer_rasterlage_kein_pfeil(self):
        feld = bild('begleiter_pfeil')
        # Bereits zwei Pixel nach rechts lösten zuvor einen Gegnerpfeil aus:
        # (0.684375, 0.238889), nach fünf Pixeln nach unten (0.684375, 0.25).
        for dy in range(6):
            for dx in range(6):
                with self.subTest(dx=dx, dy=dy):
                    self.assertEqual(reflexe.gegner_pfeile(np.roll(feld, (dy, dx), axis=(0, 1))), [])

    def test_zwei_echte_pfeile_bei_anderer_rasterlage(self):
        feld = bild('kampf_pfeile')
        for dx, dy in ((0, 0), (2, 0), (2, 5)):
            with self.subTest(dx=dx, dy=dy):
                pfeile = reflexe.gegner_pfeile(np.roll(feld, (dy, dx), axis=(0, 1)))
                self.assertEqual(len(pfeile), 2)
                self.assertTrue(all(x > 0.6 for x, y in pfeile))

    def test_echte_pfeile_bei_anderer_aufloesung(self):
        feld = bild('kampf_pfeile')
        for breite, hoehe in ((640, 360), (1440, 810)):
            with self.subTest(aufloesung=(breite, hoehe)):
                skaliert = np.asarray(Image.fromarray(feld).resize((breite, hoehe), Image.Resampling.BILINEAR))
                self.assertEqual(len(reflexe.gegner_pfeile(skaliert)), 2)


if __name__ == '__main__':
    unittest.main()
