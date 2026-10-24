"""0.16: Truhen immer öffnen, Teleport in eine andere Region, Karte langsam.

Livelauf 23:00 (Inazuma, „Go to the Grand Bazaar“ 7 km): Nach dem Kampf lag eine Truhe am Strand.
„F ▸ Common Chest“ galt als Gespräch (Truhensymbol ähnelte der Sprechblase), und weil das Questziel
weit weg war, wollte er sofort teleportieren. Die Kartensuche fand das Ziel in Sumeru nie: Das
goldene Randsymbol links oben (Klick springt zum Ziel) lag in einem gesperrten Bereich.

Bilder aus logs/diag (F10 von Nikola), wie im Bot auf 960x540 verkleinert, UID geschwärzt.
"""
from pathlib import Path
import queue
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
sys.path.insert(0, str(SRC))
import reflexe
import app
from tests.test_genshin_reflexe import info, Uhr
from tests.test_genshin_kartensuche import Kartenwelt, pin

BILDER = Path(__file__).with_name('genshin_bilder')
OHNE_TRUHE = ('stadt', 'oberwelt_nacht', 'spur_und_npc', 'f_hinweis_npc', 'domaene_raute_ornament',
              'domaene_gegner', 'wueste_klettern', 'kampf_pfeile_rechts_gras', 'venti_q_bereit',
              'gleiten_pardis', 'tracker_caravan_ribat')


def bild(name):
    return np.asarray(Image.open(BILDER / f'{name}.jpg').convert('RGB'))


class TruhenErkennung(unittest.TestCase):
    def test_truhensymbol_in_der_welt(self):
        x, y, _ = reflexe.truhe(bild('truhe_11m'))
        self.assertAlmostEqual(x, .338, delta=.01)
        self.assertAlmostEqual(y, .461, delta=.01)
        x, _, _ = reflexe.truhe(bild('truhe_rand_pfeil'))  # außerhalb: Symbol mit Pfeil rechts
        self.assertGreater(x, .78)
        self.assertIsNotNone(reflexe.truhe(bild('truhe_nach_kampf')))  # 21:56, andere Truhe/Gegend

    def test_kein_truhensymbol_ohne_truhe(self):
        for name in OHNE_TRUHE:
            with self.subTest(name=name):
                self.assertIsNone(reflexe.truhe(bild(name)))

    def test_truhen_hinweis_ist_kein_gespraech(self):
        f = reflexe.f_hinweis(bild('truhe_f_hinweis'))
        self.assertFalse(f['gespraech'])
        self.assertTrue(f['truhe'])
        for name in ('truhe_beute', 'truhe_nach_kampf'):  # Beute aufheben
            with self.subTest(name=name):
                self.assertFalse(reflexe.f_hinweis(bild(name))['gespraech'])

    def test_npc_bleibt_gespraech(self):
        for name in ('f_hinweis_npc', 'spur_und_npc'):
            with self.subTest(name=name):
                f = reflexe.f_hinweis(bild(name))
                self.assertTrue(f['gespraech'])
                self.assertFalse(f['truhe'])

    def test_analyse_liefert_truhe(self):
        ergebnis = reflexe.Analyse()(bild('truhe_11m'), bild('truhe_11m'), alles=True)
        self.assertIsNotNone(ergebnis['truhe'])


class KartenRandsymbol(unittest.TestCase):
    def test_goldenes_randsymbol_links_oben(self):
        for name in ('karte_inazuma_randsymbol', 'karte_inazuma_weit'):
            with self.subTest(name=name):
                x, y, _ = reflexe.quest_randmarker(bild(name))
                self.assertAlmostEqual(x, .075, delta=.01)
                self.assertAlmostEqual(y, .111, delta=.01)

    def test_freies_questsymbol_ist_kein_randsymbol(self):
        for name in ('karte', 'karte_pardis_oben', 'karte_pardis_statue', 'karte_auswahlliste',
                     'karte_m_wueste', 'karte_teleport_fenster'):
            with self.subTest(name=name):
                self.assertIsNone(reflexe.quest_randmarker(bild(name)))

    def test_herausgezoomte_karte_bleibt_karte(self):
        # Ohne Pins (Wegpunkte sind dort dunkle Rauten) brach die Suche nach dem Zoomen ab.
        self.assertTrue(reflexe.karte_offen(bild('karte_inazuma_weit')))
        for name in ('menue_domaene', 'questbuch_navigate', 'questbuch_cancel', 'stadt'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.karte_offen(bild(name)))

    def test_suche_klickt_zuerst_das_randsymbol(self):
        ziel = pin(.53, .5)
        welt = Kartenwelt([{'rand': (.075, .111, .66)},
                           {'quest': (.51, .5, .9), 'pins': [ziel]}])
        picture, quest, treffer = welt.starten()
        self.assertEqual(welt.befehle[0], ('maus_klick', .075, .111))
        self.assertEqual(welt.befehle[1], ('warten', 1.5))
        self.assertEqual(quest, (.51, .5, .9))
        self.assertEqual(treffer, [ziel])

    def test_randsymbol_ist_nicht_das_ziel(self):
        # Erkennt raute() das Randsymbol selbst als Quest, darf kein Wegpunkt daneben gewählt werden.
        welt = Kartenwelt([{'rand': (.9, .5, .7), 'quest': (.905, .5, .8), 'pins': [pin(.88, .52)]},
                           {'quest': (.5, .5, .9), 'pins': [pin(.52, .5)]}])
        _, quest, treffer = welt.starten()
        self.assertEqual(welt.befehle[0][0], 'maus_klick')
        self.assertEqual(quest, (.5, .5, .9))
        self.assertEqual(treffer[0]['x'], .52)


class TruhenSteuerung(unittest.TestCase):
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

    def test_truhe_vor_teleport(self):
        # Questziel am Minimap-Rand (Teleport nach 8 s), aber eine Truhe ist zu sehen.
        befehle, modi = self.lauf(0, 20, ziel=(300, .95), truhe=(.34, .46, .99))
        self.assertNotIn(('teleport',), befehle)
        self.assertEqual(modi, {'zur Truhe'})
        blicke = [b[1] for b in befehle if b[0] == 'blick']
        self.assertTrue(blicke and blicke[0] < 0)  # Truhe links: nach links drehen
        self.assertIn(('halten', 'w'), befehle)

    def test_truhen_hinweis_wird_geoeffnet_auch_bei_fernem_ziel(self):
        befehle, modi = self.lauf(0, 3, ziel=(300, .95), truhe=(.55, .39, .99),
                                  f_hinweis={'y': .5, 'gespraech': False, 'truhe': True})
        self.assertIn(('tippen', 'f'), befehle)
        self.assertNotIn(('teleport',), befehle)
        self.assertIn('Truhe öffnen', modi)

    def test_beute_nach_der_truhe_aufheben_dann_weiter(self):
        self.lauf(0, 1, f_hinweis={'y': .5, 'gespraech': False, 'truhe': True})
        befehle, modi = self.lauf(1, 4, ziel=(300, .95), f_hinweis={'y': .47, 'gespraech': False, 'truhe': False})
        self.assertIn(('tippen', 'f'), befehle)
        self.assertIn('Beute aufheben', modi)
        befehle, _ = self.lauf(4, 30, ziel=(300, .95))
        self.assertIn(('teleport',), befehle)  # erst danach weiter zur Quest

    def test_fremder_f_hinweis_ohne_kampf_nicht_vorrangig(self):
        # Statue/Wegpunkt/Laden: kein Dauer-F vor dem Questlauf (sonst Menüs auf und zu).
        befehle, _ = self.lauf(0, 2, ziel=(0, .5), f_hinweis={'y': .5, 'gespraech': False, 'truhe': False})
        self.assertNotIn('Beute aufheben', self.pilot.modus)

    def test_unerreichbare_truhe_nach_40_s_aufgeben(self):
        self.lauf(0, 41, schritt=.25, ziel=(300, .5), truhe=(.5, .4, .9))
        _, modi = self.lauf(41, 50, schritt=.25, ziel=(300, .5), truhe=(.5, .4, .9))
        self.assertNotIn('zur Truhe', modi)

    def test_f_hoechstens_zehnmal_dann_pause(self):
        befehle, _ = self.lauf(0, 12, f_hinweis={'y': .5, 'gespraech': False, 'truhe': True})
        self.assertLessEqual(befehle.count(('tippen', 'f')), 10)

    def test_karte_zu_neuer_teleport_nach_20_s(self):
        befehle, _ = self.lauf(0, 10, ziel=(300, .95))
        self.assertEqual(befehle.count(('teleport',)), 1)
        self.pilot.teleport_bald_wieder()
        befehle, _ = self.lauf(10, 40, ziel=(300, .95))
        self.assertEqual(befehle.count(('teleport',)), 1)  # nicht erst nach 3 min


class KarteGehtSpaetAuf(unittest.TestCase):
    def setUp(self):
        self.instance = object.__new__(app.App)
        self.instance.messages = queue.Queue()
        self.instance.command = Mock(return_value=True)
        self.instance.close_menus = Mock(return_value=False)
        self.instance.save_diag = Mock()

    def test_karte_nach_mehreren_sekunden(self):
        # Livelauf 22:55: Die Karte kam erst nach ~8 s – früher gab er nach 3 Bildern auf.
        bilder = [bild('stadt')] * 12 + [bild('karte_pardis_oben')] + [bild('karte')] * 4 + [bild('karte_teleport_fenster')]
        look = Mock(side_effect=bilder)
        self.assertTrue(self.instance.teleport(look, 'spiel'))

    def test_karte_kommt_nie_diagnose_und_kennung(self):
        look = Mock(return_value=bild('stadt'))
        self.assertFalse(self.instance.teleport(look, 'spiel'))
        self.assertEqual(look.call_count, 20)
        self.assertEqual(self.instance.save_diag.call_args.args[1]['modus'], 'Teleport: Karte ging nicht auf')
        self.assertEqual(self.instance.teleport_fehler, 'karte_zu')


class KarteHineinzoomen(unittest.TestCase):
    """Livelauf 23:18: Quest auf Sumeru-Stadt, Stadt-Wegpunkte erst nah sichtbar – er nahm eine
    Statue weit draußen und stürzte beim Weg in die Stadt ab."""

    def test_ferner_wegpunkt_dann_hineinzoomen(self):
        import kartensuche
        statue, stadt = pin(.42, .6, art='statue'), pin(.52, .51)  # wie 23:18: 0,19 vom Ziel
        welt = Kartenwelt([{'quest': (.51, .5, .9), 'pins': [statue]},
                           {'quest': (.51, .5, .9), 'pins': [stadt, pin(.2, .8)]}])
        _, _, treffer = welt.starten()
        self.assertIn(('karte_zoom', kartensuche.ZOOM_RASTEN), welt.befehle)
        self.assertEqual(treffer[0], stadt)

    def test_naher_wegpunkt_kein_zoom(self):
        welt = Kartenwelt([{'quest': (.51, .5, .9), 'pins': [pin(.53, .5)]}])
        welt.starten()
        self.assertEqual(welt.befehle, [])

    def test_ohne_ziel_nach_zoom_wieder_zurueck(self):
        import kartensuche
        statue = pin(.42, .6, art='statue')
        welt = Kartenwelt([{'quest': (.51, .5, .9), 'pins': [statue]},
                           {'quest': (.51, .5, .9), 'pins': []},
                           {'quest': (.51, .5, .9), 'pins': [statue]}])
        _, _, treffer = welt.starten()
        zooms = [o[1] for o in welt.befehle if o[0] == 'karte_zoom']
        self.assertEqual(zooms, [kartensuche.ZOOM_RASTEN, -kartensuche.ZOOM_RASTEN])
        self.assertEqual(treffer, [statue])

    def test_zoombefehl_mehrere_rastungen(self):
        import threading
        instance = object.__new__(app.App)
        instance.stop = threading.Event()
        target = (1, {'left': 0, 'top': 0, 'width': 1920, 'height': 1080})
        with patch.object(app, 'window', return_value=target), patch.object(app.user32, 'SetCursorPos', return_value=1), \
                patch.object(app.win_input, 'mouse') as maus:
            self.assertTrue(app.App.command(instance, ('karte_zoom', 12), target))
            self.assertEqual(maus.call_count, 12)
            with self.assertRaises(ValueError):
                app.App.command(instance, ('karte_zoom', 40), target)


class GleiterFlackern(unittest.TestCase):
    def test_kurz_nicht_erkannter_gleiter_wird_nicht_zugeklappt(self):
        uhr = Uhr()
        pilot = reflexe.Pilot(600, uhr=uhr)
        befehle = []
        for i in range(30):  # gleitet …
            uhr.t = i * .1
            befehle += pilot.tick(info(gleitet=True))
        for i in range(30, 40):  # … Erkennung flackert, Bild sieht nach Fall aus
            uhr.t = i * .1
            befehle += pilot.tick(info(faellt=True, gleitet=False))
        self.assertNotIn(('tippen', 'space'), befehle)

    def test_echter_fall_oeffnet_gleiter_weiterhin(self):
        uhr = Uhr()
        pilot = reflexe.Pilot(600, uhr=uhr)
        self.assertIn(('tippen', 'space'), pilot.tick(info(faellt=True)))


if __name__ == '__main__':
    unittest.main()
