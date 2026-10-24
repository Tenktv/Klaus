"""Erkundungsmodus: Ziele aus der HoYoLAB-Datenbank, Kompasskurs, Koppelnavigation, Karte als Peilung."""
from pathlib import Path
import json
import queue
import sys
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent'
sys.path.insert(0, str(SRC))
import erkunden
import reflexe
import app
from tests.test_genshin_reflexe import info, Uhr

BILDER = Path(__file__).with_name('genshin_bilder')


def bild(name):
    return np.asarray(Image.open(BILDER / f'{name}.jpg').convert('RGB'))


def ziel(x, y, typ='Common Chest', id_=1):
    return {'id': id_, 'art': 'truhe', 'typ': typ, 'x_pos': x, 'y_pos': y, 'z_level': 0}


class ErkunderLogik(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.uhr = Uhr()
        self.e = erkunden.Erkunder(datei=Path(self.tmp.name) / 'erkundet.json', uhr=self.uhr)

    def tearDown(self):
        self.tmp.cleanup()

    def test_kurs_genordet(self):
        self.e.position_neu(0, 0, 1.0)
        for (x, y), kurs in (((0, -100), 0), ((100, 0), 90), ((0, 100), 180), ((-100, 0), 270)):
            with self.subTest(ziel=(x, y)):
                self.e.ziel = ziel(x, y)
                self.assertAlmostEqual(self.e.kurs(), kurs, delta=.1)

    def test_koppelnavigation_und_neu_peilen(self):
        self.e.position_neu(0, 0)
        self.e.ziel = ziel(0, -200)
        self.assertFalse(self.e.peilung_noetig())
        self.e.laufen(10)
        self.assertAlmostEqual(self.e.abstand(), 200 - 10 * self.e.geschwindigkeit, delta=.1)
        self.e.laufen(16)
        self.assertTrue(self.e.peilung_noetig())  # nach 25 s Laufzeit

    def test_geschwindigkeit_wird_gelernt(self):
        self.e.position_neu(0, 0)
        self.e.laufen(10)
        self.uhr.t = 10
        self.e.position_neu(0, -80)  # 8 m/s gemessen
        self.assertGreater(self.e.geschwindigkeit, 6)
        self.e.laufen(10)
        self.e.position_neu(0, -2000)  # Ausreißer (Teleport): nicht lernen
        self.assertLess(self.e.geschwindigkeit, 7)

    def test_ziel_aus_der_datenbank_und_erledigt_merken(self):
        # Standort aus dem echten Kartenbild Inazuma (Tatarasuna), siehe test_position_aus_karte.
        self.e.position_neu(2421, 6349)
        erstes = self.e.ziel_waehlen()
        self.assertIsNotNone(erstes)
        self.assertIn(erstes['art'], ('truhe', 'sammeln'))
        self.e.erledigen('besucht')
        gespeichert = json.loads(self.e.datei.read_text(encoding='utf-8'))
        self.assertEqual(gespeichert[str(erstes['id'])]['grund'], 'besucht')
        zweites = erkunden.Erkunder(datei=self.e.datei, uhr=self.uhr)
        zweites.position_neu(2421, 6349)
        self.assertNotEqual(zweites.ziel_waehlen()['id'], erstes['id'])


class ErkundenPilot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr, teleport=True)
        self.pilot.erkunder = erkunden.Erkunder(datei=Path(self.tmp.name) / 'e.json', uhr=self.uhr)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ohne_position_erst_karte(self):
        self.assertIn(('position',), self.pilot.tick(info(ziel=(300, .95))))

    def test_laeuft_kurs_statt_questziel_und_teleportiert_nicht(self):
        e = self.pilot.erkunder
        e.position_neu(0, 0)
        e.ziel = ziel(0, -150)  # 150 m genau nördlich
        e.ziel_seit = 0
        befehle = []
        for i in range(100):
            self.uhr.t = i * .1
            befehle += self.pilot.tick(info(ziel=(200, .95), kegel=0.0))
        self.assertIn(('halten', 'w'), befehle)
        self.assertNotIn(('teleport',), befehle)
        self.assertFalse(any(b[0] == 'blick' for b in befehle))  # Kamera zeigt schon nach Norden
        self.assertTrue(self.pilot.modus.startswith('Erkunden'))
        self.assertLess(e.abstand(), 150)

    def test_am_ziel_suchen_dann_abhaken(self):
        e = self.pilot.erkunder
        e.ziel = ziel(0, -5)
        e.ziel_seit = 0
        e.position_neu(0, 0)  # Peilung am Ziel = Kartenbeweis
        befehle = []
        for i in range(120):
            self.uhr.t = i * .1
            befehle += self.pilot.tick(info(kegel=0.0))
        self.assertTrue(any(b[0] == 'blick' for b in befehle))  # Spirale
        self.assertIn('1', e.erledigt)

    def test_sammelobjekt_am_ziel_mit_f(self):
        e = self.pilot.erkunder
        e.ziel = ziel(0, -5)
        e.ziel_seit = 0
        e.position_neu(0, 0)  # Peilung am Ziel = Kartenbeweis
        befehle = self.pilot.tick(info(f_hinweis={'y': .5, 'gespraech': False, 'truhe': False}))
        self.assertIn(('tippen', 'f'), befehle)

    def test_geschaetzte_ankunft_braucht_kartenbeweis(self):
        # Livelauf 22:29: nach Schätzung „am Ziel“, tatsächlich 17 m entfernt – Suche am falschen Ort.
        e = self.pilot.erkunder
        e.position_neu(0, 0)
        e.ziel = ziel(0, -20)
        e.ziel_seit = 0
        befehle = []
        for i in range(40):
            self.uhr.t = i * .1
            befehle += self.pilot.tick(info(kegel=0.0))
        self.assertIn(('position',), befehle)
        self.assertNotIn('am Ziel', self.pilot.modus)
        self.assertNotIn('1', e.erledigt)

    def test_feststecken_zaehlt_nicht_als_weg(self):
        e = self.pilot.erkunder
        e.position_neu(0, 0)
        e.ziel = ziel(0, -100)
        e.ziel_seit = 0
        for i in range(30):
            self.uhr.t = i * .1
            self.pilot.tick(info(kegel=0.0, bewegt=False))
        self.assertGreater(e.abstand(), 95)

    def test_unerreichbar_nach_zeitlimit(self):
        e = self.pilot.erkunder
        e.position_neu(0, 0)
        e.ziel = ziel(0, -300)
        e.ziel_seit = 0
        e.ziel_dauer = erkunden.ZIEL_ZEIT + 1
        self.pilot.tick(info(kegel=0.0))
        self.assertEqual(e.erledigt['1']['grund'], 'unerreichbar')

    def test_kampfzeit_zaehlt_nicht_gegen_die_zielgrenze(self):
        e = self.pilot.erkunder
        e.position_neu(0, 0)
        e.ziel = ziel(0, -300)
        e.ziel_seit = 0
        for i in range(1700):  # 170 s Kampf
            self.uhr.t = i * .1
            self.pilot.tick(info(kegel=0.0, gegner=(.5, .3, .08)))
        self.assertFalse(e.ziel_abgelaufen())
        self.assertNotIn('1', e.erledigt)

    def test_fehlgeschlagene_peilung_15_s_pause(self):
        e = self.pilot.erkunder
        self.assertIn(('position',), self.pilot.tick(info(kegel=0.0)))
        e.peilung_fehlgeschlagen()
        befehle = []
        for i in range(1, 140):
            self.uhr.t = i * .1
            befehle += self.pilot.tick(info(kegel=0.0))
        self.assertNotIn(('position',), befehle)  # 14 s: keine neue Karte
        self.assertIn(('halten', 'w'), befehle)   # aber weiterlaufen
        self.uhr.t = 16
        self.assertIn(('position',), self.pilot.tick(info(kegel=0.0)))


class Freischalten(unittest.TestCase):
    """Teleportpunkte/Statuen nur ansteuern, wenn die Karte sie grau (gesperrt) zeigt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.uhr = Uhr()
        self.e = erkunden.Erkunder(arten=('teleport', 'statue', 'domaene'),
                                   datei=Path(self.tmp.name) / 'e.json', uhr=self.uhr)
        import raetsel_db
        self.wegpunkt = next(p for p in raetsel_db.punkte() if p['art'] == 'teleport')

    def tearDown(self):
        self.tmp.cleanup()

    def test_nur_gesperrte_wegpunkte_als_ziel(self):
        w = self.wegpunkt
        self.e.position_neu(w['x_pos'] + 60, w['y_pos'])
        ziel = self.e.ziel_waehlen()
        self.assertTrue(ziel is None or ziel['id'] != w['id'])  # Status unbekannt: nicht hin
        self.e.kartenstatus([(w['x_pos'] + 3, w['y_pos'] - 2, False, 'wegpunkt')])
        self.assertIn(w['id'], self.e.gesperrt)
        self.assertEqual(self.e.ziel_waehlen()['id'], w['id'])

    def test_blauer_wegpunkt_wird_abgehakt(self):
        w = self.wegpunkt
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], True, 'wegpunkt')])
        self.assertEqual(self.e.erledigt[str(w['id'])]['grund'], 'schon frei')

    def test_nach_besuch_noch_grau_zweiter_versuch(self):
        w = self.wegpunkt
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], False, 'wegpunkt')])
        self.e.position_neu(w['x_pos'] + 5, w['y_pos'])
        self.e.ziel_waehlen()
        self.e.erledigen('besucht')
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], False, 'wegpunkt')])
        self.assertNotIn(str(w['id']), self.e.erledigt)       # zweiter Versuch
        self.e.ziel_waehlen()
        self.e.erledigen('besucht')
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], False, 'wegpunkt')])
        self.assertIn(str(w['id']), self.e.erledigt)          # danach nicht mehr

    def test_schon_frei_bleibt_schon_frei(self):
        w = self.wegpunkt
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], True, 'wegpunkt')])
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], True, 'wegpunkt')])
        self.assertEqual(self.e.erledigt[str(w['id'])]['grund'], 'schon frei')

    def test_freigeschaltet_nach_besuch(self):
        w = self.wegpunkt
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], False, 'wegpunkt')])
        self.e.position_neu(w['x_pos'] + 5, w['y_pos'])
        self.e.ziel_waehlen()
        self.e.erledigen('besucht')
        self.e.kartenstatus([(w['x_pos'], w['y_pos'], True, 'wegpunkt')])
        self.assertEqual(self.e.erledigt[str(w['id'])]['grund'], 'freigeschaltet')

    def test_an_domaene_kein_f_an_statue_schon(self):
        pilot = reflexe.Pilot(600, uhr=self.uhr)
        pilot.erkunder = self.e
        self.e.position_neu(0, 0)
        f = {'y': .5, 'gespraech': False, 'truhe': False}
        self.e.ziel, self.e.ziel_seit = {'id': 9, 'art': 'domaene', 'typ': 'Domain', 'x_pos': 0, 'y_pos': -5}, 0
        self.assertNotIn(('tippen', 'f'), pilot.tick(info(f_hinweis=f)))
        self.uhr.t = 1
        self.e.ziel = {'id': 8, 'art': 'statue', 'typ': 'Statue of The Seven', 'x_pos': 0, 'y_pos': -5}
        self.assertIn(('tippen', 'f'), pilot.tick(info(f_hinweis=f)))


class OkuliSchwierigkeit(unittest.TestCase):
    """Echte Community-Hinweise aus der Datenbank."""

    def test_schwere_okuli(self):
        for hinweis in ('Use nearby snowball launcher aimed high then jump out and glide',
                        'In midair. Transform into a blue kuuhenki and enter the red mist to warp up',
                        'On top of the cliff', 'Locked behind a world quest (Disputes Without Honor)',
                        'Floating above the building.', 'Use a qucusaur to reach it',
                        'Climb the dead tree to collect.', 'In a cave below the waterfall'):
            with self.subTest(hinweis=hinweis):
                self.assertTrue(erkunden.schwer({'art': 'sammeln', 'hinweis': hinweis}))

    def test_leichte_okuli_und_truhen(self):
        for hinweis in ('Between the two palm trees.', 'Next to the wolf!',
                        'On the train tracks next to the waypoint', 'At the end of the dock near an exquisite chest', ''):
            with self.subTest(hinweis=hinweis):
                self.assertFalse(erkunden.schwer({'art': 'sammeln', 'hinweis': hinweis}))
        self.assertFalse(erkunden.schwer({'art': 'truhe', 'typ': 'Common Chest'}))


class PinStatus(unittest.TestCase):
    def test_inazuma_freie_pins_nicht_grau(self):
        # Früher galten hier viele freie Pins als grau (Raute an anderer Stelle bei dieser Zoomstufe).
        ziele = reflexe.teleportziele(bild('karte_inazuma_randsymbol'))
        self.assertGreaterEqual(sum(z['offen'] for z in ziele), 15)
        self.assertEqual([z for z in ziele if z['sicher'] and not z['offen']], [])

    def test_sumeru_gesperrte_pins(self):
        ziele = reflexe.teleportziele(bild('karte'))
        self.assertGreaterEqual(sum(1 for z in ziele if z['sicher'] and not z['offen']), 5)
        # Pin unter dem Questsymbol: nicht einstufbar
        mitte = min(ziele, key=lambda z: abs(z['x'] - .5) + abs(z['y'] - .51))
        self.assertFalse(mitte['sicher'])


class GegnerBestaetigen(unittest.TestCase):
    """Natlan 22:58: Glanzlichter auf roten Felsen galten als Gegnerbalken – er schlug ins Leere."""

    def test_einzelner_treffer_ist_kein_gegner(self):
        from unittest.mock import patch
        uhr = Uhr()
        analyse = reflexe.Analyse(uhr=uhr)
        feld = bild('stadt')
        with patch.object(reflexe, 'gegner', side_effect=[(.29, .54, .014), None, None, None]):
            ergebnisse = []
            for i in range(4):
                uhr.t = i * .12
                ergebnisse.append(analyse(feld, feld)['gegner'])
        self.assertEqual(ergebnisse, [None, None, None, None])

    def test_zweimal_an_derselben_stelle_ist_gegner(self):
        from unittest.mock import patch
        uhr = Uhr()
        analyse = reflexe.Analyse(uhr=uhr)
        feld = bild('stadt')
        with patch.object(reflexe, 'gegner', side_effect=[(.5, .3, .06), (.52, .31, .06)]):
            uhr.t = 0
            erstes = analyse(feld, feld)['gegner']
            uhr.t = .12
            zweites = analyse(feld, feld)['gegner']
        self.assertIsNone(erstes)
        self.assertIsNotNone(zweites)


class WenigHp(unittest.TestCase):
    def test_ohne_kampf_wenig_hp_figur_wechseln(self):
        uhr = Uhr()
        pilot = reflexe.Pilot(600, uhr=uhr)
        befehle = pilot.tick(info(eigene_hp=.12, ziel=(0, .5)))
        self.assertIn(('tippen', '2'), befehle)
        uhr.t = 1
        self.assertNotIn(('tippen', '3'), pilot.tick(info(eigene_hp=.12, ziel=(0, .5))))  # nicht sofort weiter


class PositionMitVorwissen(unittest.TestCase):
    """Natlan 22:55: nur 2-5 freie Symbole – der volle Abgleich (6 Symbole, 2 Statuen) scheiterte."""

    def setUp(self):
        import kartenatlas, kartenspieler, raetsel_db
        self.atlas, self.db = kartenatlas, raetsel_db
        self.karte = bild('karte_pardis_oben')
        self.t = kartenatlas.lokalisieren(self.karte)
        self.pfeil = kartenspieler.spieler(self.karte)[:2]
        self.wahr = raetsel_db.atlas_position(self.t, *self.pfeil, 960, 540)

    def test_ungefaehre_position_reicht(self):
        import math
        for fehler in ((80, 0), (0, -120), (100, 100)):
            with self.subTest(fehler=fehler):
                t2 = self.atlas.lokalisieren_nahe(self.karte, self.pfeil, (self.wahr[0] + fehler[0], self.wahr[1] + fehler[1]),
                                                  self.t['scale'], 1.0)
                pos = self.db.atlas_position(t2, *self.pfeil, 960, 540)
                self.assertLess(math.hypot(pos[0] - self.wahr[0], pos[1] - self.wahr[1]), 3)

    def test_einzelnes_symbol_nie_falsch(self):
        import math
        from unittest.mock import patch
        alle = reflexe.teleportziele(self.karte)
        for z in alle:
            with patch.object(reflexe, 'teleportziele', return_value=[z]):
                t2 = self.atlas.lokalisieren_nahe(self.karte, self.pfeil, (self.wahr[0] + 90, self.wahr[1] - 60),
                                                  self.t['scale'], 1.0)
            if t2 is not None:
                pos = self.db.atlas_position(t2, *self.pfeil, 960, 540)
                self.assertLess(math.hypot(pos[0] - self.wahr[0], pos[1] - self.wahr[1]), 15)

    def test_zoom_nach_versuchen_zurueck(self):
        from unittest.mock import patch
        instance = object.__new__(app.App)
        instance.messages = queue.Queue()
        instance.command = Mock(return_value=True)
        instance.close_menus = Mock(return_value=False)
        instance.save_diag = Mock()
        look = Mock(side_effect=[bild('karte_inazuma_weit')] * 6)
        with patch.object(instance, 'position_merken', return_value=None):
            self.assertIsNone(instance.position_bestimmen(look, 'spiel'))
        zooms = [c.args[0][1] for c in instance.command.call_args_list if c.args[0][0] == 'karte_zoom']
        self.assertEqual(sum(zooms), 0)  # gleich viel hinein wie heraus: Maßstab bleibt
        self.assertEqual(len(zooms), 6)


class DiagnoseBleibt(unittest.TestCase):
    """Nikola: Diagnosebilder „sollen bleiben“ – früher hielt er nur 40 und löschte nach Uhrzeit-Namen."""

    def test_nichts_wird_geloescht(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'DIAG', Path(tmp)):
            instance = object.__new__(app.App)
            alt = Path(tmp) / '235959.jpg'
            alt.write_bytes(b'x')  # Bild von gestern spät, Name sortiert nach heute
            for _ in range(45):
                instance.save_diag(bild('stadt'), {'modus': 'test'})
            self.assertTrue(alt.exists())
            tage = [d for d in Path(tmp).iterdir() if d.is_dir()]
            self.assertEqual(len(tage), 1)
            self.assertGreaterEqual(len(list(tage[0].glob('*.jpg'))), 1)


class PositionAusKarte(unittest.TestCase):
    def test_position_aus_karte(self):
        instance = object.__new__(app.App)
        instance.messages = queue.Queue()
        instance.command = Mock(return_value=True)
        instance.close_menus = Mock(return_value=False)
        instance.save_diag = Mock()
        look = Mock(side_effect=[bild('stadt'), bild('karte_inazuma_randsymbol')])
        stand = instance.position_bestimmen(look, 'spiel')
        self.assertIsNotNone(stand)
        self.assertAlmostEqual(stand[0], 2421, delta=15)
        self.assertAlmostEqual(stand[1], 6349, delta=15)
        instance.close_menus.assert_called_once()
        self.assertEqual(instance.command.call_args_list[0].args[0], ('tippen', 'm', 0.08))


if __name__ == '__main__':
    unittest.main()
