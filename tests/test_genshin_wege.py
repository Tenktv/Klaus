"""V-Partikel und anhaltende Umwege statt sofort wieder zur Hauswand laufen."""
import unittest

from tests.test_genshin_reflexe import bild, info, Uhr, reflexe


class Wege(unittest.TestCase):
    def setUp(self):
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr)

    def test_nikolas_spur_fuehrt_zuerst_links_um_die_begrenzung(self):
        ziel = reflexe.spur(bild('v_spur_stadt_kurve'))
        self.assertIsNotNone(ziel)
        self.assertLess(ziel[0], .28)
        self.assertGreater(ziel[1], .37)  # naher Abschnitt, nicht das entfernte Ende nach der Kurve

    def test_folgt_partikeln_statt_durch_den_pfeiler_zum_marker(self):
        spur = reflexe.spur(bild('v_spur_stadt_kurve'))
        befehle = self.pilot.tick(info(ziel=(90, .8), spur=spur, spur_frisch=True))
        self.assertEqual(self.pilot.modus, 'folgt V-Spur')
        self.assertTrue(any(b[0] == 'blick' and b[1] < 0 for b in befehle))

    def test_sichtbare_spur_geht_auch_nahe_am_ziel_weiter(self):
        befehle = self.pilot.tick(info(ziel=(90, .09), spur=(.23, .45), spur_frisch=True))
        self.assertEqual(self.pilot.modus, 'folgt V-Spur')
        self.assertTrue(any(b[0] == 'blick' and b[1] < 0 for b in befehle))

    def test_spur_kurz_weg_nicht_sofort_zum_marker_zuruecklenken(self):
        self.pilot.tick(info(ziel=(90, .8), spur=(.23, .45), spur_frisch=True))
        self.uhr.t = .4
        befehle = self.pilot.tick(info(ziel=(90, .8), spur=None))
        self.assertEqual(self.pilot.modus, 'V-Spur kurz verdeckt')
        self.assertFalse(any(b[0] == 'blick' and b[1] > 0 for b in befehle))

    def test_umweg_spur_hoechstens_8_sekunden_dann_luftlinie(self):
        # Vor dem Kampf (21:53) zeigte die Spur dauernd weg vom Ziel; er drehte sich im Kreis.
        modi = []
        for i in range(120):  # 12 s: Spur links, Ziel rechts (110° Abweichung), nie festgesteckt
            self.uhr.t = i*.1
            self.pilot.tick(info(ziel=(90, .8), spur=(.23, .45), spur_frisch=True))
            modi.append(self.pilot.modus)
        self.assertEqual(modi[0], 'folgt V-Spur')
        self.assertTrue(all(m != 'folgt V-Spur' for m in modi[100:]))
        self.assertEqual(modi[-1], 'laufen')

    def test_spur_richtung_ziel_wird_immer_befolgt(self):
        for i in range(150):
            self.uhr.t = i*.1
            self.pilot.tick(info(ziel=(350, .8), kegel=0.0, spur=(.45, .45), spur_frisch=True))
        self.assertEqual(self.pilot.modus, 'folgt V-Spur')

    def test_sichtbare_spur_auch_wenn_minimapmarker_kurz_fehlt(self):
        befehle = self.pilot.tick(info(ziel=None, spur=(.23, .45), spur_frisch=True))
        self.assertEqual(self.pilot.modus, 'folgt V-Spur')
        self.assertTrue(any(b[0] == 'blick' and b[1] < 0 for b in befehle))

    def test_v_nicht_im_kampf_oder_beim_gleiten(self):
        for i in range(40):
            self.uhr.t = i*.1
            kampf = self.pilot.tick(info(ziel=(90, .8), gegner=(.5, .4, .06)))
            self.assertNotIn(('tippen', 'v'), kampf)
        self.pilot = reflexe.Pilot(600, uhr=self.uhr)
        self.assertNotIn(('tippen', 'v'), self.pilot.tick(info(ziel=(90, .8), gleitet=True)))

    def test_umweg_haelt_seitlichen_kurs(self):
        self.pilot.befreiungen = 1
        self.pilot._umweg_starten(info(ziel=(90, .8), kegel=90), 0)
        self.uhr.t = 1.8
        befehle = self.pilot.tick(info(ziel=(90, .8), kegel=170))
        self.assertEqual(self.pilot.modus, 'Hindernis seitlich umgehen')
        self.assertIn(('halten', 'w'), befehle)
        self.assertFalse(any(b[0] == 'blick' and b[1] < 0 for b in befehle))

    def test_wieder_fest_versucht_andere_seite(self):
        self.pilot.befreiungen = 1
        self.pilot._umweg_starten(info(ziel=(90, .8), kegel=90), 0)
        zuerst = self.pilot.umweg['seite']
        self.pilot._befreien(info(ziel=(90, .8), kegel=170), 2)
        self.assertEqual(self.pilot.umweg['seite'], -zuerst)

    def test_sonnenglanz_rechts_ist_nicht_naechster_spurpunkt(self):
        ziel = reflexe.spur(bild('spur_und_npc'))
        self.assertIsNotNone(ziel)
        self.assertLess(ziel[0], .35)  # echter Weg links; vereinzelter Glanz rechts ignoriert


if __name__ == '__main__':
    unittest.main()
