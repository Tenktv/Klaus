"""Öffentlicher Atlas: echte Kartenbilder und bewusst mehrdeutige Geometrie."""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'))
import kartenatlas

BILDER = Path(__file__).with_name('genshin_bilder')


def bild(name):
    return np.asarray(Image.open(BILDER / (name + '.jpg')).convert('RGB'))


def beispiel():
    xy = [(0, 0), (180, 110), (42, 91), (143, 8), (95, 142), (11, 173), (221, 75), (175, 190)]
    nodes = [dict(id=i, x_pos=x, y_pos=y, label_id=2 if i < 2 else 3)
             for i, (x, y) in enumerate(xy)]
    punkte = [dict(x=(n['x_pos']+180)/960, y=(n['y_pos']+100)/540,
                   art='statue' if n['label_id'] == 2 else 'wegpunkt', offen=True)
              for n in nodes]
    return nodes, punkte


class KartenatlasTests(unittest.TestCase):
    def test_echte_karten_registrieren_mit_vielen_unabhaengigen_pins(self):
        for name, mindestens, scale in [('karte_pardis_statue', 20, .3334),
                                       ('karte_pardis_oben', 21, .2682),
                                       ('karte', 35, .2685),
                                       ('karte_m_wueste', 32, .2684)]:
            with self.subTest(name=name):
                result = kartenatlas.lokalisieren(bild(name))
                self.assertIsNotNone(result)
                self.assertGreaterEqual(result['treffer'], mindestens)
                self.assertLess(result['fehler'], 2)
                self.assertAlmostEqual(result['scale'], scale, delta=.002)
                self.assertEqual(result['y_sign'], 1)

    def test_spielwelt_wird_nicht_als_atlas_position_akzeptiert(self):
        self.assertIsNone(kartenatlas.lokalisieren(bild('oberwelt_nacht')))

    def test_zu_wenige_oder_nur_eine_statue(self):
        nodes, punkte = beispiel()
        self.assertIsNone(kartenatlas.registrieren(punkte[:5], nodes=nodes))
        self.assertIsNone(kartenatlas.registrieren(punkte[1:], nodes=nodes))

    def test_eindeutiges_geometrisches_muster(self):
        nodes, punkte = beispiel()
        result = kartenatlas.registrieren(punkte, nodes=nodes)
        self.assertIsNotNone(result)
        self.assertEqual(result['treffer'], 8)
        self.assertAlmostEqual(result['scale'], 1)
        self.assertAlmostEqual(result['offset_x'], 180)
        self.assertAlmostEqual(result['offset_y'], 100)

    def test_doppeltes_katalogmuster_ist_mehrdeutig(self):
        nodes, punkte = beispiel()
        zweites = [dict(n, id=n['id']+100, x_pos=n['x_pos']+5000) for n in nodes]
        self.assertIsNone(kartenatlas.registrieren(punkte, nodes=nodes+zweites))

    def test_gleicher_pin_kann_nicht_sechs_treffer_erzeugen(self):
        nodes, punkte = beispiel()
        self.assertIsNone(kartenatlas.registrieren(punkte[:2]+[punkte[2]]*8, nodes=nodes))

    def test_verschobene_zufaellige_symbole_sind_keine_position(self):
        nodes, punkte = beispiel()
        rng = np.random.default_rng(19)
        for p in punkte:
            p['x'], p['y'] = rng.uniform(.1, .9, 2)
        self.assertIsNone(kartenatlas.registrieren(punkte, nodes=nodes))

    def test_katalog_enthaelt_keine_freischaltbehauptung(self):
        result = kartenatlas.lokalisieren(bild('karte_pardis_statue'))
        for p in kartenatlas.naechstgelegene(.5, .5, result):
            self.assertIsNone(p['freigeschaltet'])
            self.assertNotIn('author_name', p)
        self.assertEqual(kartenatlas.naechstgelegene(.5, .5, None), [])


if __name__ == '__main__':
    unittest.main()
