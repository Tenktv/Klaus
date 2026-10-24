"""Luft- und Kampfsteuerung: reale UI-Bilder, simulierte Bewegung, keine Spieleingaben."""
from pathlib import Path
import json
import queue
import sys
import tempfile

import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
sys.path.insert(0, str(SRC))
import reflexe
import app
from tests.test_genshin_reflexe import info, Uhr

BILDER = Path(__file__).with_name('genshin_bilder')


def bild(name):
    return np.asarray(Image.open(BILDER / (name+'.jpg')).convert('RGB'))


class LuftErkennung(unittest.TestCase):
    def test_echter_geoeffneter_gleiter(self):
        feld = bild('gleiten_pardis')
        self.assertTrue(reflexe.gleitet(feld))
        self.assertFalse(reflexe.faehigkeitstaste_sichtbar(feld))
        result = reflexe.Analyse()(feld, feld, alles=True)
        self.assertTrue(result['gleitet'])
        self.assertFalse(result['gleiter_zu'])

    def test_andere_icons_sind_keine_offenen_gleiter(self):
        for name in ('hutao_e_bereit', 'kampf_pfeil_links', 'begleiter_pfeil',
                     'stadt', 'wueste_klettern', 'dialog_hell', 'karte', 'ladebild'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.gleitet(bild(name)))
        self.assertTrue(reflexe.faehigkeitstaste_sichtbar(bild('hutao_e_bereit')))

    def test_1080p_gleiter(self):
        feld = np.asarray(Image.fromarray(bild('gleiten_pardis')).resize((1920, 1080)))
        self.assertTrue(reflexe.gleitet(feld))

    def test_im_flug_keine_teuren_gegner_oder_spursuchen(self):
        feld = bild('gleiten_pardis')
        with patch.object(reflexe, 'gegner', side_effect=AssertionError('erst Luft sichern')), \
                patch.object(reflexe, 'spur', side_effect=AssertionError('erst Luft sichern')):
            for _ in range(4):
                self.assertTrue(reflexe.Analyse()(feld, feld, alles=True)['gleitet'])

    def test_fall_trotz_feststehendem_hud_und_seitlicher_bewegung(self):
        # Keine Aufzeichnung eines echten Falls: Weltbewegung auf einem echten
        # Hintergrund simulieren, HUD/Figur bleiben wie im Spiel unverändert.
        feld = bild('begleiter_pfeil')
        for dx in (0, 16):
            fall = reflexe.Fall()
            ergebnis = []
            for i in range(4):
                neu = np.roll(feld, (-12*i, dx*i), axis=(0, 1)).copy()
                for x0, y0, x1, y1 in reflexe.HUD:
                    a, b, c, d = round(x0*960), round(y0*540), round(x1*960), round(y1*540)
                    neu[b:d, a:c] = feld[b:d, a:c]
                ergebnis.append(fall.update(neu))
            self.assertTrue(ergebnis[1], (dx, ergebnis))

    def test_reines_drehen_und_stillstand_sind_kein_fall(self):
        feld = bild('begleiter_pfeil')
        for dx in (0, 16):
            fall = reflexe.Fall()
            self.assertFalse(any(fall.update(np.roll(feld, dx*i, axis=1)) for i in range(4)))

    def test_fall_reset_nach_pause(self):
        fall = reflexe.Fall()
        feld = bild('begleiter_pfeil')
        fall.update(feld)
        fall.reset()
        self.assertFalse(fall.update(np.roll(feld, -12, axis=0)))


class LuftSteuerung(unittest.TestCase):
    def setUp(self):
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr, teleport=True)

    def test_nutzer_hat_gleiter_schon_geoeffnet(self):
        for i in range(25):
            self.uhr.t = i*.1
            befehle = self.pilot.tick(info(faellt=True, gleitet=True, bewegt=False,
                                          gegner=(.5, .3, .06), ziel=(90, 1.0)))
            self.assertNotIn(('tippen', 'space'), befehle)
            self.assertNotIn(('klick',), befehle)
            self.assertNotIn(('teleport',), befehle)
            self.assertEqual(self.pilot.modus, 'gleiten')

    def test_fall_hat_vorrang_vor_kampf_und_festhaengen(self):
        befehle = []
        for i in range(25):
            self.uhr.t = i*.1
            befehle += self.pilot.tick(info(faellt=True, gegner=(.5, .3, .06),
                                           bewegt=False, ziel=(90, 1.0)))
        self.assertEqual(befehle.count(('tippen', 'space')), 1)
        self.assertFalse(any(b[0] in ('klick', 'ausweichen', 'teleport') for b in befehle))
        self.assertFalse(any(b[0] == 'tippen' and b[1] in ('q', 'e', 'f') for b in befehle))

    def test_ein_fehlerbild_oeffnet_gleiter_nicht_erneut(self):
        self.pilot.tick(info(faellt=True))
        self.uhr.t = .1
        self.pilot.tick(info(faellt=False))
        self.uhr.t = .2
        self.assertNotIn(('tippen', 'space'), self.pilot.tick(info(faellt=True)))

    def test_nach_bestaetigter_landung_neuer_fall(self):
        self.pilot.tick(info(faellt=True))
        self.uhr.t = 1
        self.pilot.tick(info(faellt=False))
        self.uhr.t = 1.9
        self.pilot.tick(info(faellt=False))
        self.uhr.t = 2
        self.assertIn(('tippen', 'space'), self.pilot.tick(info(faellt=True)))

    def test_maximal_ein_bestaetigter_wiederholversuch(self):
        befehle = []
        for i in range(25):
            self.uhr.t = i*.1
            befehle += self.pilot.tick(info(faellt=True, gleiter_zu=True))
        self.assertEqual(befehle.count(('tippen', 'space')), 2)

    def test_geoeffneter_gleiter_verhindert_wiederholversuch(self):
        self.pilot.tick(info(faellt=True))
        self.uhr.t = .6
        self.assertNotIn(('tippen', 'space'), self.pilot.tick(info(faellt=True, gleitet=True)))


class KampfSteuerung(unittest.TestCase):
    def setUp(self):
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr)

    def test_echter_linker_richtungspfeil_wird_erkannt(self):
        pfeile = reflexe.gegner_pfeile(bild('kampf_pfeil_links'))
        self.assertEqual(len(pfeile), 1)
        self.assertAlmostEqual(pfeile[0][0], .244, delta=.02)
        befehle = self.pilot.tick(info(pfeile=pfeile))
        self.assertTrue(any(b[0] == 'blick' and b[1] < 0 for b in befehle))
        self.assertNotIn(('klick',), befehle)  # nie gesehener Gegner: erst zum Pfeil drehen
    def test_im_kampf_wird_jedes_bild_frisch_geprueft(self):
        feld = bild('hutao_e_bereit')
        analyse = reflexe.Analyse(uhr=self.uhr)
        with patch.object(reflexe, 'gegner', side_effect=[(.5, .3, .06), None]) as suchen:
            erste = analyse(feld, feld)
            self.uhr.t = .12
            zweite = analyse(feld, feld)
        self.assertTrue(erste['gegner_frisch'])
        self.assertTrue(zweite['gegner_frisch'])
        self.assertIsNone(zweite['gegner'])
        self.assertEqual(suchen.call_count, 2)

    def test_greift_an_waehrend_er_ausrichtet(self):
        # Normalangriffe zielen von allein auf den nächsten Gegner; früher drehte er nur noch,
        # während ihn die Gegner trafen (HP 63 % -> 5 % bei fast keinem Angriff).
        self.pilot.zuletzt['wechsel'] = 0
        self.pilot.kampf_bis = 1  # Kampf läuft schon (zu Beginn käme erst E)
        befehle = self.pilot.tick(info(gegner=(.97, .3, .05)))
        self.assertTrue(any(b[0] == 'blick' and b[1] > 0 for b in befehle))
        self.assertIn(('klick',), befehle)
    def test_altes_gegnerbild_dreht_nicht_neu(self):
        self.pilot.zuletzt['wechsel'] = 0
        self.pilot.kampf_bis = 1
        befehle = self.pilot.tick(info(gegner=(.97, .3, .05), gegner_frisch=False))
        self.assertFalse(any(b[0] == 'blick' for b in befehle))  # Position vom alten Bild
        self.assertIn(('klick',), befehle)
    def test_verlorenes_ziel_kurz_weiterkaempfen_dann_begrenzt_umsehen(self):
        self.pilot.zuletzt['wechsel'] = 0
        self.pilot.tick(info(gegner=(.5, .3, .05)))
        self.uhr.t = .5
        befehle = self.pilot.tick(info())
        self.assertIn(('klick',), befehle)                     # meist nur kurz verdeckt
        self.assertFalse(any(b[0] == 'blick' for b in befehle))
        blicke = 0
        for i in range(60):  # danach kurz umsehen, spätestens 3 s ohne Gegner zurück zur Quest
            self.uhr.t = 2.0 + i*.2
            blicke += sum(1 for b in self.pilot.tick(info()) if b[0] == 'blick')
        self.assertTrue(1 <= blicke <= 3)  # früher: 60° alle 0,7 s, endlos
        self.assertNotIn('kampf', self.pilot.modus)
    def test_naher_gegner_wird_sofort_angegriffen(self):
        # Neuer Kampf: zuerst E mit der aktuellen Figur, gleich danach Normalangriffe.
        self.pilot.zuletzt['wechsel'] = 0
        befehle = self.pilot.tick(info(gegner=(.5, .3, .08)))
        self.assertEqual(befehle, [('tippen', 'e')])
        self.uhr.t = .1
        befehle = self.pilot.tick(info(gegner=(.5, .3, .08)))
        self.assertIn(('klick',), befehle)
        self.assertNotIn(('halten', 'w'), befehle)
    def test_entfernter_gegner_wird_angelaufen_statt_in_die_luft_schiessen(self):
        self.pilot.zuletzt['wechsel'] = 0
        befehle = self.pilot.tick(info(gegner=(.5, .2, .02)))
        self.assertIn(('halten', 'w'), befehle)
        self.assertNotIn(('klick',), befehle)
    def test_gegner_bleibt_in_der_bildmitte_erkennbar(self):
        ziel = reflexe.gegner(bild('domaene_gegner'))
        self.assertIsNotNone(ziel)
        self.assertAlmostEqual(ziel[0], .568, delta=.025)

    def test_figurwechsel_reihum_mit_e_und_q(self):
        tasten = []
        for i in range(400):
            self.uhr.t = i*.1
            tasten += [b[1] for b in self.pilot.tick(info(gegner=(.5, .3, .08), q_bereit=i % 70 > 30))
                       if b[0] == 'tippen']
        self.assertTrue({'2', '3', '4', 'e', 'q'} <= set(tasten))
        self.assertFalse('5' in tasten)
        self.assertGreaterEqual(tasten.count('2'), 2)
    def test_hp_verlust_loest_begrenztes_ausweichen_aus(self):
        self.pilot.tick(info(gegner=(.5, .3, .05), eigene_hp=.9))
        self.uhr.t = .4
        befehle = self.pilot.tick(info(gegner=(.5, .3, .05), eigene_hp=.7))
        self.assertTrue(any(b[0] == 'ausweichen' for b in befehle))
        self.assertNotIn(('klick',), befehle)
        self.uhr.t = .5
        nachher = self.pilot.tick(info(gegner=(.5, .3, .05), eigene_hp=.7))
        self.assertFalse(any(b[0] == 'ausweichen' for b in nachher))
        self.assertIn(('klick',), nachher)  # danach sofort weiterkämpfen, nicht dauerhaft ausweichen
    def test_pfeile_allein_loesen_kein_ausweichen_aus(self):
        befehle = []
        for i in range(60):
            self.uhr.t = i*.1
            befehle += self.pilot.tick(info(pfeile=[(.2, .4)]))
        self.assertEqual(len([b for b in befehle if b[0] == 'ausweichen']), 0)
        self.assertNotIn(('klick',), befehle)
    def test_hp_nur_eigener_balken(self):
        self.assertGreater(reflexe.eigene_hp(bild('hutao_e_bereit')), .9)
        hp = reflexe.eigene_hp(bild('kampf_pfeil_links'))
        self.assertGreater(hp, .6)
        self.assertLess(hp, .8)
        self.assertIsNone(reflexe.eigene_hp(bild('karte')))

    def test_gegner_balkenmitte_statt_einzelnes_rotes_stueck(self):
        from tests.test_genshin_reflexe import welt, mit_balken
        ziel = reflexe.gegner(mit_balken(welt(), x=600, y=150, breite=80))
        self.assertIsNotNone(ziel)
        self.assertAlmostEqual(ziel[0], 640/960, delta=.01)
        self.assertAlmostEqual(ziel[2], 80/960, delta=.01)

    def test_ausweichen_gibt_tasten_auch_bei_stopp_frei(self):
        instance = object.__new__(app.App)
        instance.stop = Mock(is_set=Mock(return_value=False), wait=Mock(return_value=True))
        target = (1, {})
        with patch.object(app, 'window', return_value=target), patch.object(app.win_input, 'key') as key:
            self.assertFalse(app.App.command(instance, ('ausweichen', 'a', .1), target))
        self.assertEqual(key.call_args_list[-2].args, (app.VK['shift'],))
        self.assertEqual(key.call_args_list[-1].args, (app.VK['a'],))
        self.assertTrue(key.call_args_list[-2].kwargs['up'])
        self.assertTrue(key.call_args_list[-1].kwargs['up'])

    def test_diagnosefolge_speichert_vorherige_bilder_im_tempordner(self):
        instance = object.__new__(app.App)
        instance.messages = queue.Queue()
        frames = [(bild('hutao_e_bereit'), {'faellt': False}),
                  (bild('gleiten_pardis'), {'faellt': True, 'gleitet': True})]
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'DIAG', Path(tmp)):
            instance.save_trace(frames, 'gleiten')
            dateien = list(Path(tmp).glob('verlauf/*/zustand.json'))
            self.assertEqual(len(dateien), 1)
            daten = json.loads(dateien[0].read_text(encoding='utf-8'))
            self.assertEqual(len(daten['bilder']), 2)
            self.assertTrue(daten['bilder'][1]['gleitet'])


if __name__ == '__main__':
    unittest.main()
