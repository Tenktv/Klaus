"""Kartensuche mit simulierten Kartenbildern, ohne echte Eingaben oder KI."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'))
import kartensuche


def pin(x, y, offen=True, art='wegpunkt'):
    return {'x': x, 'y': y, 'offen': offen, 'art': art, 'abstand': 0.0}


class Kartenwelt:
    """Nur ausgeführte Zoom-/Ziehbefehle verändern die simulierte Aufnahme."""
    def __init__(self, szenen):
        self.szenen = szenen
        self.index = 0
        self.befehle = []
        self.aufnahmen = []
        self.bilder = [np.full((90, 160, 3), i, np.uint8) for i in range(len(szenen))]

    def command(self, order):
        self.befehle.append(order)
        if order[0] != 'warten':
            self.index = min(self.index + 1, len(self.szenen) - 1)
        return True

    def look(self):
        self.aufnahmen.append(self.index)
        return self.bilder[self.index]

    def szene(self, picture):
        return self.szenen[int(picture[0, 0, 0])]

    def starten(self, **kwargs):
        with patch.object(kartensuche.reflexe, 'karte_offen',
                          side_effect=lambda p: self.szene(p).get('offen', True)), \
             patch.object(kartensuche.reflexe, 'raute',
                          side_effect=lambda p, **k: self.szene(p).get('quest')), \
             patch.object(kartensuche.reflexe, 'quest_randmarker',
                          side_effect=lambda p: self.szene(p).get('rand')), \
             patch.object(kartensuche.reflexe, 'teleportziele',
                          side_effect=lambda p: self.szene(p).get('pins', [])):
            return kartensuche.suchen(self.bilder[0], self.look, self.command, Mock(), **kwargs)


class KartensucheTest(unittest.TestCase):
    def test_entfernter_freier_punkt_wenn_er_die_reststrecke_verkuerzt(self):
        feld = np.zeros((90, 160, 3), np.uint8)
        frei = pin(.6, .3)
        gesperrt = pin(.79, .2, False)
        with patch.object(kartensuche.reflexe, 'teleportziele', return_value=[frei, gesperrt]), \
                patch.object(kartensuche.kartenspieler, 'spieler', return_value=(.1, .8, .95)):
            auswahl = kartensuche.kandidaten(feld, (.8, .2, .9))
        self.assertEqual(len(auswahl), 1)
        self.assertEqual(auswahl[0]['x'], frei['x'])
        self.assertGreater(auswahl[0]['weg_ersparnis'], .2)

    def test_kein_entfernter_teleport_ohne_spielerposition(self):
        feld = np.zeros((90, 160, 3), np.uint8)
        with patch.object(kartensuche.reflexe, 'teleportziele', return_value=[pin(.6, .3)]), \
                patch.object(kartensuche.kartenspieler, 'spieler', return_value=None):
            self.assertEqual(kartensuche.kandidaten(feld, (.8, .2, .9)), [])

    def test_kein_teleport_ohne_deutliche_wegverkuerzung(self):
        feld = np.zeros((90, 160, 3), np.uint8)
        with patch.object(kartensuche.reflexe, 'teleportziele', return_value=[pin(.2, .75)]), \
                patch.object(kartensuche.kartenspieler, 'spieler', return_value=(.1, .8, .95)):
            self.assertEqual(kartensuche.kandidaten(feld, (.8, .2, .9)), [])

    def test_sichtbares_ziel_braucht_keine_eingaben_und_filtert_sperren(self):
        nah = pin(.53, .5, art='statue')
        weiter = pin(.6, .5)
        welt = Kartenwelt([{'quest': (.51, .5, .9),
                           'pins': [weiter, pin(.52, .5, False), pin(.9, .5), nah]}])
        picture, quest, treffer = welt.starten()
        self.assertIs(picture, welt.bilder[0])
        self.assertEqual(quest, (.51, .5, .9))
        self.assertEqual(treffer, [nah, weiter])
        self.assertIs(treffer[0], nah)
        self.assertEqual(welt.befehle, [])

    def test_offscreen_quest_beim_zoom_finden_dann_detailgrad_pruefen(self):
        ziel = pin(.55, .5)
        welt = Kartenwelt([{}, {'quest': (.51, .5, .9)},
                           {'quest': (.51, .5, .9), 'pins': [ziel]}])
        picture, quest, treffer = welt.starten()
        self.assertIs(picture, welt.bilder[2])
        self.assertEqual(treffer, [ziel])
        self.assertEqual([o for o in welt.befehle if o[0] == 'karte_zoom'],
                         [('karte_zoom', -kartensuche.ZOOM_RASTEN), ('karte_zoom', kartensuche.ZOOM_RASTEN)])
        self.assertEqual(welt.aufnahmen, [1, 2])

    def test_kartenausschnitt_ziehen_findet_quest_ausserhalb_des_ueberblicks(self):
        ziel = pin(.55, .5)
        welt = Kartenwelt([{}, {}, {}, {},
                           {'quest': (.51, .5, .9), 'pins': [ziel]}])
        picture, quest, treffer = welt.starten()
        self.assertIs(picture, welt.bilder[4])
        self.assertEqual(treffer, [ziel])
        ziehen = [o for o in welt.befehle if o[0] == 'karte_ziehen']
        self.assertEqual(len(ziehen), 1)
        self.assertAlmostEqual(ziehen[0][1] - ziehen[0][3], .45)

    def test_zentrieren_verwirft_alte_quest_und_pin_koordinaten(self):
        alter_pin, neuer_pin = pin(.92, .5), pin(.53, .5)
        welt = Kartenwelt([{'quest': (.9, .5, .9), 'pins': [alter_pin]},
                           {'quest': (.51, .5, .9), 'pins': [neuer_pin]}])
        picture, quest, treffer = welt.starten()
        self.assertIs(picture, welt.bilder[1])
        self.assertEqual(quest[:2], (.51, .5))
        self.assertEqual(treffer, [neuer_pin])
        self.assertNotIn(alter_pin, treffer)
        self.assertEqual(welt.aufnahmen, [1])

    def test_detailzoom_benutzt_erst_die_nachher_frisch_erkannten_pins(self):
        neuer_pin = pin(.53, .52)
        welt = Kartenwelt([{}, {'quest': (.8, .5, .9)},
                           {'quest': (.51, .5, .9)},
                           {'quest': (.51, .5, .9), 'pins': [neuer_pin]}])
        picture, quest, treffer = welt.starten()
        self.assertIs(picture, welt.bilder[3])
        self.assertEqual(treffer, [neuer_pin])
        self.assertEqual([o[0] for o in welt.befehle if o[0] != 'warten'],
                         ['karte_zoom', 'karte_ziehen', 'karte_zoom'])

    def test_stopp_bei_befehl_verwirft_treffer(self):
        welt = Kartenwelt([{'quest': (.9, .5, .9), 'pins': [pin(.92, .5)]}])
        welt.command = Mock(return_value=False)
        picture, quest, treffer = welt.starten()
        self.assertIsNone(quest)
        self.assertEqual(treffer, [])
        self.assertEqual(welt.aufnahmen, [])
        self.assertEqual(welt.command.call_count, 1)

    def test_stopp_in_wartezeit_macht_keine_weitere_aufnahme(self):
        welt = Kartenwelt([{}])
        welt.command = Mock(side_effect=[True, False])
        _, quest, treffer = welt.starten()
        self.assertIsNone(quest)
        self.assertEqual(treffer, [])
        self.assertEqual(welt.aufnahmen, [])

    def test_keine_karte_sendet_keine_eingaben(self):
        welt = Kartenwelt([{'offen': False}])
        _, quest, treffer = welt.starten()
        self.assertIsNone(quest)
        self.assertEqual(treffer, [])
        self.assertEqual(welt.befehle, [])

    def test_karte_verloren_stoppt_vor_naechster_eingabe(self):
        welt = Kartenwelt([{}, {'offen': False}])
        _, quest, treffer = welt.starten()
        self.assertIsNone(quest)
        self.assertEqual(treffer, [])
        self.assertEqual(len(welt.befehle), 2)
        self.assertEqual(welt.aufnahmen, [1])

    def test_unterbrechungen_werden_nicht_verschluckt(self):
        welt = Kartenwelt([{}])
        welt.command = Mock(side_effect=KeyboardInterrupt)
        with self.assertRaises(KeyboardInterrupt):
            welt.starten()

    def test_keinen_fund_auf_25_rasteransichten_begrenzen(self):
        welt = Kartenwelt([{}])
        _, quest, treffer = welt.starten()
        self.assertIsNone(quest)
        self.assertEqual(treffer, [])
        self.assertEqual(len([o for o in welt.befehle if o[0] == 'karte_zoom']), 3)
        self.assertEqual(len([o for o in welt.befehle if o[0] == 'karte_ziehen']), 24)
        self.assertEqual(len(welt.aufnahmen), 27)

    def test_zeitlimit_verhindert_weitere_eingaben(self):
        welt = Kartenwelt([{}])
        with patch.object(kartensuche.time, 'monotonic', side_effect=[0.0, 0.0, 61.0]):
            _, quest, treffer = welt.starten()
        self.assertIsNone(quest)
        self.assertEqual(treffer, [])
        self.assertEqual(welt.befehle, [])

    def test_diagnose_bekommt_das_aktuelle_bild(self):
        welt = Kartenwelt([{}, {'quest': (.51, .5, .9), 'pins': [pin(.53, .5)]}])
        diagnose = Mock()
        welt.starten(diagnose=diagnose)
        self.assertIs(diagnose.call_args_list[0].args[0], welt.bilder[0])
        self.assertIs(diagnose.call_args_list[-1].args[0], welt.bilder[1])
        self.assertEqual(diagnose.call_args.args[1]['kandidaten'], 1)

    def test_spirale_besucht_jeden_ausschnitt_einmal(self):
        felder = list(kartensuche._spirale())
        self.assertEqual(len(felder), 25)
        self.assertEqual(set(felder), {(x, y) for x in range(-2, 3) for y in range(-2, 3)})
        for a, b in zip(felder, felder[1:]):
            self.assertEqual(abs(a[0]-b[0]) + abs(a[1]-b[1]), 1)

    def test_atlas_gibt_nur_suchrichtung_und_klickt_keinen_unbestaetigten_punkt(self):
        frisch = pin(.53, .5)
        welt = Kartenwelt([{'quest': (.78, .5, .9)},
                           {'quest': (.51, .5, .9), 'pins': [frisch]}])
        transform = dict(scale=1., offset_x=0., offset_y=0., y_sign=1., treffer=8, fehler=1.)
        with patch.object(kartensuche.kartenatlas, 'lokalisieren', return_value=transform), \
                patch.object(kartensuche.kartenatlas, 'naechstgelegene',
                             return_value=[dict(x_pos=144., y_pos=45., freigeschaltet=None)]):
            _, _, treffer = welt.starten()
        self.assertEqual(treffer, [frisch])  # erst nach neuer Sichtprüfung ein echtes freies Ziel
        self.assertEqual([b[0] for b in welt.befehle if b[0] != 'warten'], ['karte_ziehen'])

    def test_fehlender_atlas_blockiert_bildsuche_nicht(self):
        welt = Kartenwelt([{'quest': (.51, .5, .9), 'pins': [pin(.53, .5)]}])
        with patch.object(kartensuche.kartenatlas, 'lokalisieren', side_effect=OSError('Cache fehlt')):
            _, _, treffer = welt.starten()
        self.assertEqual(len(treffer), 1)
        self.assertEqual(welt.befehle, [])


if __name__ == '__main__':
    unittest.main()
