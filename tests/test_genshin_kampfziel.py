"""0.15: Kampfziel halten, Warnpfeile rundum, Q nutzen.

Livelauf 22:10 („Defeat all opponents 0/6“): Er verlor die Gegner aus dem Bild, sah die Warnpfeile
hinter sich nicht (Bildmitte war gesperrt, Farbe korallrot statt rosa) und lief nach drei Umsehern
zum 1344 m entfernten Questmarker – verfolgt von den Gegnern. Ventis Q war bereit, wurde aber nur
0,25 s nach E gedrückt und ging in der E-Animation verloren.

Bilder aus logs/diag (F10), wie im Bot auf 960x540 verkleinert, farbtreu gespeichert, UID geschwärzt.
"""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
sys.path.insert(0, str(SRC))
import reflexe
from tests.test_genshin_reflexe import info, Uhr

BILDER = Path(__file__).with_name('genshin_bilder')
OHNE_KAMPF = ('stadt', 'oberwelt_nacht', 'spur_und_npc', 'spur_oberwelt', 'domaene_raute_ornament',
              'wueste_klettern', 'tracker_caravan_ribat', 'gleiten_pardis')


def bild(name):
    return np.asarray(Image.open(BILDER / f'{name}.jpg').convert('RGB'))


def richtungen(name):
    return [reflexe.pfeil_winkel(x, y) for x, y in reflexe.gegner_pfeile(bild(name))]


class Warnpfeile(unittest.TestCase):
    def test_korallrote_pfeile_auf_gras_rechts(self):
        winkel = richtungen('kampf_pfeile_rechts_gras')
        self.assertEqual(len(winkel), 3)
        self.assertTrue(all(70 < w < 130 for w in winkel), winkel)

    def test_pfeile_unter_der_figur_heissen_gegner_hinten(self):
        # Früher war die Bildmitte unterhalb y=0,10 ganz gesperrt: genau hier liegen sie.
        winkel = richtungen('kampf_pfeile_hinten')
        self.assertEqual(len(winkel), 3)
        self.assertTrue(all(abs(w) > 150 for w in winkel), winkel)
        links = richtungen('kampf_pfeil_hinten_links')  # Bild nicht in den Vorlagen enthalten
        self.assertEqual(len(links), 1)
        self.assertLess(links[0], -140)

    def test_pfeile_im_moment_der_aufgabe(self):
        # 22:10:28 „sucht Gegner“, Rekorder: pfeile=[] – tatsächlich standen sie vorn links,
        # rechts und hinten rechts.
        winkel = sorted(richtungen('kampf_suche_pfeile'))
        self.assertEqual(len(winkel), 3)
        self.assertLess(winkel[0], -10)
        self.assertGreater(winkel[-1], 90)

    def test_keine_pfeile_ohne_kampf(self):
        for name in OHNE_KAMPF:
            with self.subTest(name=name):
                self.assertEqual(reflexe.gegner_pfeile(bild(name)), [])

    def test_alte_testpfeile_weiter(self):
        self.assertEqual(len(reflexe.gegner_pfeile(bild('kampf_pfeile'))), 2)
        self.assertEqual(len(reflexe.gegner_pfeile(bild('kampf_pfeil_links'))), 1)
        self.assertEqual(reflexe.gegner_pfeile(bild('begleiter_pfeil')), [])

    def test_pfeilwinkel(self):
        self.assertAlmostEqual(reflexe.pfeil_winkel(.5, .13), 0, delta=1)
        self.assertAlmostEqual(reflexe.pfeil_winkel(.766, .5), 90, delta=1)
        self.assertAlmostEqual(abs(reflexe.pfeil_winkel(.5, .87)), 180, delta=1)
        self.assertAlmostEqual(reflexe.pfeil_winkel(.234, .5), -90, delta=1)


class KampfzielErkennung(unittest.TestCase):
    def test_defeat_im_questtracker(self):
        for name in ('kampf_pfeile_rechts_gras', 'kampf_pfeile_hinten', 'venti_q_bereit',
                     'kampf_pfeil_links'):  # Hauptquest, unterstrichen: „Defeat the attacking Fatui“
            with self.subTest(name=name):
                self.assertTrue(reflexe.kampfziel(bild(name)))

    def test_andere_questziele_sind_kein_kampf(self):
        for name in OHNE_KAMPF + ('am_ziel_tempel', 'dialog_hell', 'karte'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.kampfziel(bild(name)))

    def test_1080p(self):
        feld = np.asarray(Image.fromarray(bild('kampf_pfeile_rechts_gras')).resize((1920, 1080)))
        self.assertTrue(reflexe.kampfziel(feld))


class QErkennung(unittest.TestCase):
    def test_q_knopf_bereit(self):
        for name in ('venti_q_bereit', 'vodyanitsa_q_bereit', 'begleiter_pfeil'):
            with self.subTest(name=name):
                self.assertTrue(reflexe.q_bereit(bild(name)))

    def test_q_knopf_ladend_oder_abklingzeit(self):
        for name in ('kampf_pfeile_rechts_gras', 'kampf_pfeile_hinten', 'q_abklingzeit', 'stadt', 'hutao_e_bereit'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.q_bereit(bild(name)))

    def test_teamleiste(self):
        # Hu Tao aktiv (graues Nummernfeld), Ventis Q leuchtet neben seinem Namen.
        self.assertEqual(reflexe.team_status(bild('kampf_pfeile_rechts_gras')), (1, (3,)))
        self.assertEqual(reflexe.team_status(bild('kampf_pfeil_hinten_links')), (1, (3,)))
        # Vodyanitsa aktiv mit eigenem Q bereit, Hu Taos Q in der Teamleiste.
        self.assertEqual(reflexe.team_status(bild('vodyanitsa_q_bereit')), (2, (1,)))
        self.assertEqual(reflexe.team_status(bild('venti_q_bereit')), (3, ()))
        self.assertEqual(reflexe.team_status(bild('stadt'))[1], ())

    def test_analyse_liefert_alles(self):
        ergebnis = reflexe.Analyse()(bild('kampf_pfeile_hinten'), bild('kampf_pfeile_hinten'), alles=True)
        self.assertEqual(len(ergebnis['pfeile']), 3)
        self.assertTrue(ergebnis['kampfziel'])
        self.assertFalse(ergebnis['q_bereit'])
        self.assertEqual((ergebnis['team_aktiv'], ergebnis['team_q']), (1, (3,)))


class KampfzielSteuerung(unittest.TestCase):
    def setUp(self):
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr, teleport=True)

    def lauf(self, von, bis, schritt=.1, **werte):
        befehle, modi = [], set()
        t = von
        while t < bis:
            self.uhr.t = t
            befehle += self.pilot.tick(info(**werte))
            modi.add(self.pilot.modus)
            t += schritt
        return befehle, modi

    def test_offenes_kampfziel_haelt_ihn_im_kampf(self):
        # Nachgestellt 22:10: Gegner gesehen, dann weg; Questziel am Minimap-Rand, V-Spur sichtbar.
        self.lauf(0, 5, gegner=(.5, .3, .05), ziel=(9, .82), kampfziel=True)
        befehle, modi = self.lauf(5, 65, ziel=(9, .95), spur=(.8, .6), kampfziel=True)
        self.assertTrue(all(m.startswith('kampf') for m in modi), modi)
        self.assertNotIn(('teleport',), befehle)
        self.assertTrue(any(b[0] == 'blick' for b in befehle))   # sucht rundum
        self.assertIn(('halten', 'w'), befehle)                   # und geht dabei ein Stück

    def test_ohne_kampfziel_wie_bisher_zurueck_zur_quest(self):
        self.lauf(0, 5, gegner=(.5, .3, .05), ziel=(9, .5))
        _, modi = self.lauf(5, 15, ziel=(9, .5))
        self.assertFalse(self.pilot.modus.startswith('kampf'), modi)

    def test_kampfziel_ohne_gegnerspur_bindet_nicht(self):
        # „Defeat all opponents“ steht da, die Gegner sind aber noch am Questziel: hinlaufen.
        _, modi = self.lauf(0, 5, ziel=(30, .5), kampfziel=True)
        self.assertFalse(any(m.startswith('kampf') for m in modi), modi)

    def test_kampfziel_gibt_nach_90_s_ohne_gegner_frei(self):
        self.lauf(0, 2, gegner=(.5, .3, .05), kampfziel=True)
        self.lauf(2, 80, schritt=.25, ziel=(9, .5), kampfziel=True)
        self.assertTrue(self.pilot.modus.startswith('kampf'))
        self.lauf(80, 100, schritt=.25, ziel=(9, .5), kampfziel=True)
        self.assertFalse(self.pilot.modus.startswith('kampf'))

    def test_sucht_zuerst_in_letzter_gegnerrichtung(self):
        self.lauf(0, 2, gegner=(.8, .3, .05), kegel=0.0, kampfziel=True)  # Gegner bei etwa +22°
        befehle, _ = self.lauf(4, 9, kegel=120.0, kampfziel=True)
        blicke = [b[1] for b in befehle if b[0] == 'blick']
        self.assertTrue(blicke)
        self.assertLess(blicke[0], 0)  # von 120° zurück nach links Richtung 22°
        self.assertAlmostEqual(abs(blicke[0]) / self.pilot.zaehler_pro_grad, 98, delta=8)

    def test_pfeil_hinten_dreht_um(self):
        self.pilot.kampf_bis = 1
        befehle = self.pilot.tick(info(pfeile=[(.5, .87)]))
        blicke = [b[1] for b in befehle if b[0] == 'blick']
        self.assertEqual(len(blicke), 1)
        self.assertAlmostEqual(abs(blicke[0]) / self.pilot.zaehler_pro_grad, 180, delta=5)

    def test_pfeile_ueber_minus_180_mitteln_nicht_nach_vorn(self):
        befehle = self.pilot.tick(info(pfeile=[(.45, .86), (.55, .86)]))  # beide hinten
        blicke = [b[1] for b in befehle if b[0] == 'blick']
        self.assertAlmostEqual(abs(blicke[0]) / self.pilot.zaehler_pro_grad, 180, delta=10)

    def test_pfeil_vorn_hingehen_und_zuschlagen(self):
        befehle, _ = self.lauf(0, 1, pfeile=[(.5, .14)])
        self.assertIn(('halten', 'w'), befehle)
        self.assertIn(('klick',), befehle)
        self.assertFalse(any(b[0] == 'blick' for b in befehle))

    def test_pfeile_mit_kampfziel_unbegrenzt(self):
        # Ohne Kampfziel höchstens 6 Drehungen zu Pfeilen, mit Kampfziel weiter (Gegner jagen ihn).
        self.lauf(0, 1, gegner=(.5, .3, .05), kampfziel=True)
        befehle, modi = self.lauf(2, 40, pfeile=[(.75, .6)], kampfziel=True)
        self.assertGreater(sum(1 for b in befehle if b[0] == 'blick'), 6)
        self.assertTrue(all(m.startswith('kampf') for m in modi))


class QSteuerung(unittest.TestCase):
    def setUp(self):
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr)

    def test_kampfbeginn_e_mit_aktueller_figur_dann_q(self):
        # Früher: sofort Figur 2, E und 0,25 s später Q – Q ging in der E-Animation verloren.
        self.assertEqual(self.pilot.tick(info(gegner=(.5, .3, .08), q_bereit=True)), [('tippen', 'e')])
        tasten = []
        for i in range(1, 30):
            self.uhr.t = i * .1
            tasten += [(self.uhr.t, b[1]) for b in self.pilot.tick(info(gegner=(.5, .3, .08), q_bereit=True))
                       if b[0] == 'tippen']
        q = [t for t, taste in tasten if taste == 'q']
        self.assertTrue(q)
        self.assertGreaterEqual(q[0], .9)
        self.assertFalse(any(taste in '234' for _, taste in tasten if _ < 3.9))  # kein Sofortwechsel

    def test_kein_q_ohne_bereiten_knopf(self):
        tasten = []
        for i in range(300):
            self.uhr.t = i * .1
            tasten += [b[1] for b in self.pilot.tick(info(gegner=(.5, .3, .08))) if b[0] == 'tippen']
        self.assertNotIn('q', tasten)
        self.assertIn('e', tasten)

    def test_figur_mit_bereitem_q_kommt_frueher_dran(self):
        self.pilot.kampf_bis = 1
        self.pilot.zuletzt['wechsel'] = 0
        self.uhr.t = 2.0
        self.assertFalse(any(b[0] == 'tippen' and b[1] in '234' for b in
                             self.pilot.tick(info(gegner=(.5, .3, .08), team_aktiv=1, team_q=(3,)))))
        self.uhr.t = 2.6
        befehle = self.pilot.tick(info(gegner=(.5, .3, .08), team_aktiv=1, team_q=(3,)))
        self.assertEqual(befehle[:3], [('tippen', '3'), ('warten', .45), ('tippen', 'e')])
        self.assertEqual(self.pilot.figur, 3)
        self.uhr.t = 3.2  # E-Animation läuft noch
        self.assertNotIn(('tippen', 'q'), self.pilot.tick(info(gegner=(.5, .3, .08), q_bereit=True)))
        self.uhr.t = 4.2
        self.assertIn(('tippen', 'q'), self.pilot.tick(info(gegner=(.5, .3, .08), q_bereit=True)))

    def test_aktive_figur_aus_der_teamleiste(self):
        self.pilot.kampf_bis = 1
        self.pilot.zuletzt['wechsel'] = -10
        befehle = self.pilot.tick(info(gegner=(.5, .3, .08), team_aktiv=3))
        self.assertIn(('tippen', '4'), befehle)  # nach Platz 3 kommt 4, nicht 2


if __name__ == '__main__':
    unittest.main()
