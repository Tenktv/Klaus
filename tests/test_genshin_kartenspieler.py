"""Spielerposition auf echten, lokal gespeicherten und geschwärzten Kartenbildern."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
BILDER = Path(__file__).resolve().parent / 'genshin_bilder'
sys.path.insert(0, str(SRC))
import kartenspieler


def bild(name):
    return np.asarray(Image.open(BILDER / (name + '.jpg')).convert('RGB'))


class KartenspielerTest(unittest.TestCase):
    def test_echte_karten_mit_verschiedener_pfeilrichtung(self):
        for name, erwartet in [('karte_pardis_statue', (.5, .5)),
                               ('karte', (.439, .70)),
                               ('karte_m_wueste', (.5, .5)),
                               ('karte_pardis_oben', (.5, .5))]:
            with self.subTest(name=name):
                treffer = kartenspieler.spieler(bild(name))
                self.assertIsNotNone(treffer)
                self.assertAlmostEqual(treffer[0], erwartet[0], delta=.008)
                self.assertAlmostEqual(treffer[1], erwartet[1], delta=.008)
                self.assertGreater(treffer[2], .9)

    def test_1080p_aufloesung(self):
        original = Image.fromarray(bild('karte'))
        gross = np.asarray(original.resize((1920, 1080), Image.Resampling.BILINEAR))
        treffer = kartenspieler.spieler(gross)
        self.assertIsNotNone(treffer)
        self.assertAlmostEqual(treffer[0], .439, delta=.008)
        self.assertAlmostEqual(treffer[1], .70, delta=.008)

    def test_karte_ohne_spielerpfeil_ignoriert_wegpunkte_und_statuen(self):
        karte = bild('karte_pardis_statue').copy()
        karte[257:284, 466:492] = (80, 100, 60)
        self.assertTrue(kartenspieler.reflexe.karte_offen(karte))
        self.assertIsNone(kartenspieler.spieler(karte))

    def test_zwei_passende_pfeile_sind_mehrdeutig(self):
        karte = bild('karte_pardis_statue').copy()
        karte[355:382, 700:726] = karte[257:284, 466:492].copy()
        self.assertIsNone(kartenspieler.spieler(karte))

    def test_kreis_raute_rechteck_statt_gefuelltem_pfeil(self):
        karte = bild('karte_pardis_statue').copy()
        karte[257:284, 466:492] = (80, 100, 60)
        yy, xx = np.indices(karte.shape[:2])
        kreis = (xx-480)**2 + (yy-270)**2 < 7**2
        raute = np.abs(xx-550) + np.abs(yy-330) <= 8
        karte[kreis | raute] = (20, 220, 240)
        karte[250:263, 630:643] = (20, 220, 240)
        self.assertIsNone(kartenspieler.spieler(karte))

    def test_echte_weltbilder_werden_nicht_als_karte_behandelt(self):
        namen = [p.stem for p in BILDER.glob('*.jpg') if not p.stem.startswith('karte')]
        self.assertTrue(namen)
        for name in namen[:4]:
            with self.subTest(name=name):
                self.assertIsNone(kartenspieler.spieler(bild(name)))

    def test_ohne_bestaetigte_karte_kein_treffer(self):
        with patch.object(kartenspieler.reflexe, 'karte_offen', return_value=False):
            self.assertIsNone(kartenspieler.spieler(bild('karte_pardis_statue')))


if __name__ == '__main__':
    unittest.main()
