"""Autopilot-Reflexe: Erkennung an echten Spielbildern (tests/genshin_bilder, UID geschwärzt),
Verhalten mit künstlichen Zuständen. Keine echten Eingaben oder Screenshots."""
from pathlib import Path
import queue
import sys
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / 'src'
BILDER = Path(__file__).resolve().parent / 'genshin_bilder'
sys.path.insert(0, str(SRC / 'genshin_agent'))
import reflexe
import app


def bild(name):
    return np.asarray(Image.open(BILDER / f'{name}.jpg').convert('RGB'))


def mit_balken(feld, x=250, y=150, breite=60, schrift=True):
    """Künstlicher Gegnerbalken (6 px hoch) mit weißer „Lv.“-Schrift darüber."""
    feld = feld.copy()
    feld[y:y + 6, x:x + breite] = (247, 95, 92)
    if schrift:
        feld[y - 12:y - 4, x + 10:x + 30:3] = 255
    return feld


def karte_1080(name, mitte=(0.152, 0.113)):
    """Gespeicherten 1080p-Minimap-Ausschnitt an seine Originalstelle setzen (ältere Ausschnitte
    wurden um die frühere Mitte 0.152/0.113 geschnitten, neuere um die aktuelle)."""
    crop = np.asarray(Image.open(BILDER / f'{name}_karte.png').convert('RGB'))
    voll = np.zeros((1080, 1920, 3), np.uint8)
    x0, y0 = int(mitte[0] * 1080 - 0.087 * 1080 * 1.15), int(mitte[1] * 1080 - 0.087 * 1080 * 1.15)
    voll[y0:y0 + crop.shape[0], x0:x0 + crop.shape[1]] = crop
    return voll


def welt():
    """Unruhige, grünliche Spielwelt in 960x540."""
    rng = np.random.default_rng(1)
    feld = rng.integers(40, 90, (540, 960, 3)).astype(np.uint8)
    feld[..., 1] = np.clip(feld[..., 1].astype(int) + 50, 0, 255)
    return feld


class Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def info(**werte):
    basis = {'hud': True, 'ziel': None, 'raute': None, 'kegel': 0.0, 'gegner': None,
             'f_hinweis': None, 'spur': None, 'faellt': False,
             'dialog': False, 'laden': False, 'bewegt': True}
    basis.update(werte)
    return basis


class EchteBilder(unittest.TestCase):
    def analyse(self, name):
        feld = bild(name)
        return reflexe.analysieren(feld, feld, 'gold', reflexe.Bewegung())

    def test_spielszenen_sind_steuerbar(self):
        for name in ('stadt', 'oberwelt_nacht', 'am_ziel_tempel', 'domaene'):
            with self.subTest(name=name):
                self.assertTrue(self.analyse(name)['hud'])

    def test_dialog_menue_ladebild_sind_nicht_steuerbar(self):
        dialog, menue, laden = self.analyse('dialog_luke'), self.analyse('menue_domaene'), self.analyse('ladebild')
        self.assertFalse(dialog['hud'] or menue['hud'] or laden['hud'])
        self.assertTrue(dialog['dialog'])
        self.assertFalse(menue['dialog'] or menue['laden'])
        self.assertTrue(laden['laden'])

    def test_questziel_auf_minimap(self):
        # Im Betrieb wird das unkomprimierte 1080p-Bild ausgewertet (JPEG nimmt Sättigung weg).
        richtung, abstand = reflexe.questziel(karte_1080('oberwelt_nacht'))
        self.assertAlmostEqual(richtung, 141, delta=8)
        self.assertAlmostEqual(abstand, 0.45, delta=0.1)

    def test_questziel_in_der_wueste(self):
        # Goldgelber Sand verzog die Richtung früher auf 217° und den Abstand auf 0,64.
        richtung, abstand = reflexe.questziel(karte_1080('wueste_klettern', mitte=(reflexe.KARTE_X, reflexe.KARTE_Y)))
        self.assertAlmostEqual(richtung, 188, delta=6)
        self.assertGreater(abstand, 0.9)  # am Rand = weit weg (525 m) → Teleport

    def test_kletter_anzeige(self):
        self.assertTrue(reflexe.klettert(bild('wueste_klettern')))
        for name in ('stadt', 'oberwelt_nacht', 'spur_und_npc', 'domaene', 'domaene_dornen'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.klettert(bild(name)))
        # Symbol halb unter dem Spielerpfeil: im Betrieb wird in 1080p gemessen.
        self.assertLess(reflexe.questziel(karte_1080('am_ziel_tempel'))[1], 0.2)
        self.assertIsNone(self.analyse('domaene')['ziel'])

    def test_sichtkegel_1080p(self):
        for name, erwartet in (('oberwelt_nacht', 145), ('am_ziel_tempel', 73), ('domaene', 178)):
            with self.subTest(name=name):
                self.assertLess(abs(reflexe.winkel_diff(reflexe.kegel(karte_1080(name)), erwartet)), 10)

    def test_n_erkennung_1080p(self):
        for name in ('oberwelt_nacht', 'am_ziel_tempel', 'domaene'):
            self.assertGreater(reflexe.n_wert(karte_1080(name)), 0.8)

    def test_keine_falschen_gegner(self):
        # Feuerlinie am Boden und roter Stoffzipfel lösten früher den Kampfmodus aus.
        for name in ('stadt', 'oberwelt_nacht', 'am_ziel_tempel', 'domaene', 'domaene_feuerlinie',
                     'domaene_stoff', 'domaene_monument', 'domaene_dornen'):
            with self.subTest(name=name):
                self.assertIsNone(self.analyse(name)['gegner'])

    def test_echter_gegner_mit_levelschrift(self):
        x, y, _ = self.analyse('domaene_gegner')['gegner']
        self.assertAlmostEqual(x, 0.568, delta=0.025)  # näher an der Bildmitte liegender Gegner
        self.assertAlmostEqual(y, 0.47, delta=0.03)

    def test_goldene_raute_in_domaenen(self):
        erwartet = {'domaene_gegner': 0.19, 'domaene_feuerlinie': 0.19, 'domaene_stoff': 0.43,
                    'domaene_monument': 0.80, 'domaene_dornen': 0.47}
        for name, x in erwartet.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(self.analyse(name)['raute'][0], x, delta=0.03)

    def test_gegner_ausserhalb_des_bildes(self):
        # Kampf-Herausforderung „Opponents Defeated 1/9“: Gegner nur als rosa Rand-Pfeile sichtbar.
        pfeile = reflexe.gegner_pfeile(bild('kampf_pfeile'))
        self.assertEqual(len(pfeile), 2)
        self.assertTrue(all(x > 0.6 for x, y in pfeile))  # beide rechts
        self.assertTrue(reflexe.herausforderung(bild('kampf_pfeile')))
        self.assertTrue(reflexe.herausforderung(bild('kampf_nah')))
        for name in ('stadt', 'oberwelt_nacht', 'spur_und_npc', 'domaene_raute_ornament', 'wueste_klettern'):
            with self.subTest(name=name):
                self.assertEqual(reflexe.gegner_pfeile(bild(name)), [])   # Feuer, Blase: keine Pfeile
                self.assertFalse(reflexe.herausforderung(bild(name)))

    def test_antwortoption_in_der_wueste(self):
        # „Auto“ ausgegraut auf hellem Himmel – früher als Zwischensequenz behandelt, er wartete.
        analyse = self.analyse('dialog_wueste_antwort')
        self.assertTrue(analyse['dialog'])
        self.assertAlmostEqual(analyse['dialog_option'], 0.744, delta=0.03)
        hell = self.analyse('dialog_wueste_hell')
        self.assertTrue(hell['dialog'])
        self.assertIsNone(hell['dialog_option'])
        self.assertAlmostEqual(self.analyse('dialog_hell_optionen')['dialog_option'], 0.744, delta=0.03)

    def test_ladebild_mit_tipp_ist_kein_dialog(self):
        analyse = self.analyse('ladebild_tipp')
        self.assertTrue(analyse['laden'])
        self.assertFalse(analyse['dialog'])

    def test_helle_dialoge_am_auto_knopf(self):
        # Früher als Menü behandelt (ESC mitten im Gespräch), weil das Textband nicht dunkel war.
        for name in ('dialog_hell', 'dialog_hell_optionen', 'dialog_luke'):
            with self.subTest(name=name):
                analyse = self.analyse(name)
                self.assertTrue(analyse['dialog'])
                self.assertFalse(analyse['laden'])
        self.assertFalse(self.analyse('menue_domaene')['dialog'])

    def test_f_hinweis_mit_sprechblase(self):
        for name in ('f_hinweis_npc', 'spur_und_npc'):
            with self.subTest(name=name):
                f = self.analyse(name)['f_hinweis']
                self.assertAlmostEqual(f['y'], 0.5, delta=0.03)
                self.assertTrue(f['gespraech'])
        for name in ('stadt', 'oberwelt_nacht', 'domaene', 'domaene_monument'):
            with self.subTest(name=name):
                self.assertIsNone(self.analyse(name)['f_hinweis'])

    def test_glitzerspur_in_der_oberwelt(self):
        for name, x in (('spur_oberwelt', 0.19), ('spur_und_npc', 0.28)):
            with self.subTest(name=name):
                self.assertAlmostEqual(reflexe.spur(bild(name))[0], x, delta=0.06)
        for name in ('stadt', 'oberwelt_nacht'):
            with self.subTest(name=name):
                self.assertIsNone(reflexe.spur(bild(name)))

    def test_keine_spur_in_domaenen(self):
        # Fackelfunken sehen ähnlich aus – ohne Questsymbol auf der Minimap wird nicht gesucht.
        for name in ('domaene_feuerlinie', 'domaene_gegner'):
            with self.subTest(name=name):
                self.assertIsNone(self.analyse(name)['spur'])

    def test_raute_unter_leuchtendem_ornament(self):
        self.assertAlmostEqual(self.analyse('domaene_raute_ornament')['raute'][0], 0.27, delta=0.03)
        self.assertIsNone(self.analyse('domaene_raute_ornament')['gegner'])

    def test_schliessen_x_nur_in_menues(self):
        for name in ('karte', 'menue_domaene', 'questbuch_navigate', 'questbuch_cancel'):
            with self.subTest(name=name):
                self.assertTrue(reflexe.menue_x(bild(name)))
        for name in ('dialog_hell', 'dialog_hell_optionen', 'dialog_luke', 'ladebild', 'stadt'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.menue_x(bild(name)))

    def test_karte_und_teleport_knopf(self):
        for name in ('karte', 'karte_auswahlliste', 'karte_teleport_fenster', 'karte_quest_fenster'):
            with self.subTest(name=name):
                self.assertTrue(reflexe.karte_offen(bild(name)))
        for name in ('questbuch_navigate', 'questbuch_cancel', 'stadt', 'dialog_hell', 'domaene'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.karte_offen(bild(name)))
        self.assertTrue(reflexe.teleport_knopf(bild('karte_teleport_fenster')))
        # „Cancel Navigation“ sitzt an derselben Stelle – darf nicht als Teleport gelten.
        for name in ('karte_quest_fenster', 'karte', 'questbuch_navigate', 'stadt'):
            with self.subTest(name=name):
                self.assertFalse(reflexe.teleport_knopf(bild(name)))

    def test_freigeschaltete_teleportpunkte(self):
        punkte = reflexe.teleportpunkte(bild('karte'))
        offen = [p for p in punkte if p['offen']]
        self.assertGreaterEqual(len(offen), 8)
        self.assertGreater(len(punkte), len(offen))  # graue, gesperrte Pins werden erkannt, aber nicht genommen
        self.assertLess(offen[0]['abstand'], 0.2)    # einer liegt nah am Questziel in der Mitte

    def test_dunkles_questziel_am_oberen_kartenrand(self):
        feld = bild('karte_pardis_oben')
        self.assertTrue(reflexe.karte_offen(feld))
        self.assertIsNone(reflexe.raute(feld))  # alte Spielwelt-Maske blendet dieses Ziel aus
        ziel = reflexe.raute(feld, weltkarte=True)
        self.assertIsNotNone(ziel)
        self.assertAlmostEqual(ziel[0], .382, delta=.01)
        self.assertAlmostEqual(ziel[1], .089, delta=.01)

    def test_kartenraute_bleibt_beim_bekannten_ziel(self):
        for name in ('karte', 'karte_m_wueste'):
            with self.subTest(name=name):
                bisher = reflexe.raute(bild(name))
                jetzt = reflexe.raute(bild(name), weltkarte=True)
                self.assertIsNotNone(jetzt)
                self.assertAlmostEqual(jetzt[0], bisher[0], delta=.01)
                self.assertAlmostEqual(jetzt[1], bisher[1], delta=.01)

    def test_auswahlliste_bringt_neuen_pin(self):
        vorher = reflexe.teleportpunkte(bild('karte'))
        nachher = reflexe.teleportpunkte(bild('karte_auswahlliste'))
        neu = [q for q in nachher if all(abs(q['x'] - b['x']) + abs(q['y'] - b['y']) > 0.02 for b in vorher)]
        self.assertTrue(neu)
        self.assertAlmostEqual(neu[0]['x'], 0.676, delta=0.02)  # Eintrag „Teleport Waypoint“
        self.assertAlmostEqual(neu[0]['y'], 0.746, delta=0.02)

    def test_keine_raute_ausserhalb(self):
        for name in ('stadt', 'oberwelt_nacht', 'domaene', 'dialog_luke', 'menue_domaene', 'ladebild'):
            with self.subTest(name=name):
                feld = bild(name)
                self.assertIsNone(reflexe.raute(feld))


class KuenstlicheBilder(unittest.TestCase):
    def test_roter_lebensbalken(self):
        self.assertIsNotNone(reflexe.gegner(mit_balken(welt())))

    def test_balken_ohne_levelschrift_ist_kein_gegner(self):
        self.assertIsNone(reflexe.gegner(mit_balken(welt(), schrift=False)))

    def test_rote_flaeche_ist_kein_gegner(self):
        feld = welt()
        feld[100:160, 250:330] = (230, 50, 40)
        feld[90:98, 260:280:3] = 255
        self.assertIsNone(reflexe.gegner(feld))

    def test_roter_umhang_der_figur_ist_kein_gegner(self):
        feld = welt()
        feld[250:350, 460:500] = (230, 50, 40)
        self.assertIsNone(reflexe.gegner(feld))

    def test_kartenverschiebung(self):
        feld = welt()
        dx, dy, guete = reflexe.verschiebung(reflexe.karte_grau(feld),
                                             reflexe.karte_grau(np.roll(feld, (2, -3), axis=(0, 1))))
        self.assertEqual((dx, dy), (-3, 2))
        self.assertGreater(guete, 8)

    def test_bewegung_erkannt_und_stillstand(self):
        uhr = Uhr()
        messer = reflexe.Bewegung(uhr=uhr)
        feld = welt()
        for schritt in range(8):
            uhr.t = schritt * 0.25
            wert = messer.update(feld, np.roll(feld, schritt * 2, axis=0))
        self.assertTrue(wert)
        messer = reflexe.Bewegung(uhr=uhr)
        for schritt in range(8):
            uhr.t = 10 + schritt * 0.25
            wert = messer.update(feld, feld)
        self.assertFalse(wert)

    def test_fallerkennung(self):
        fall = reflexe.Fall()
        feld = welt()
        ergebnisse = [fall.update(np.roll(feld, -8 * schritt, axis=0)) for schritt in range(4)]
        self.assertTrue(ergebnisse[-1])  # Welt rutscht stetig nach oben = Fall
        fall = reflexe.Fall()
        self.assertFalse(any(fall.update(feld) for _ in range(4)))  # Stillstand
        fall = reflexe.Fall()
        self.assertFalse(any(fall.update(np.roll(feld, 20 * schritt, axis=1)) for schritt in range(4)))  # Drehen

    def test_bildwinkel(self):
        self.assertEqual(reflexe.bildwinkel(0.5), 0)
        self.assertAlmostEqual(reflexe.bildwinkel(1.0), reflexe.HFOV / 2, delta=0.01)
        self.assertLess(reflexe.bildwinkel(0.2), 0)


class PilotLogik(unittest.TestCase):
    def setUp(self):
        self.uhr = Uhr()
        self.pilot = reflexe.Pilot(600, uhr=self.uhr)

    def blicke(self, befehle):
        return [b for b in befehle if b[0] == 'blick']

    def test_lenkt_ueber_sichtkegel_und_laeuft(self):
        befehle = self.pilot.tick(info(ziel=(40, 1.0), kegel=0.0))
        self.assertEqual(self.blicke(befehle), [('blick', 240, 0)])
        self.assertIn(('halten', 'w'), befehle)

    def test_grosse_abweichung_erst_drehen(self):
        befehle = self.pilot.tick(info(ziel=(180, 1.0), kegel=0.0))
        self.assertTrue(self.blicke(befehle))
        self.assertNotIn(('halten', 'w'), befehle)

    def test_lernt_mauszaehler_pro_grad(self):
        self.pilot.tick(info(ziel=(40, 1.0), kegel=0.0))      # 240 Zähler für 40°
        self.uhr.t = 0.3
        self.pilot.tick(info(ziel=(40, 1.0), kegel=20.0))     # nur 20° gedreht
        self.assertGreater(self.pilot.zaehler_pro_grad, 6.0)

    def test_wartet_auf_messung_vor_neuer_drehung(self):
        self.pilot.tick(info(ziel=(40, 1.0), kegel=0.0))
        self.uhr.t = 0.1
        self.assertFalse(self.blicke(self.pilot.tick(info(ziel=(40, 1.0), kegel=0.0))))

    def test_am_ziel_ohne_f_hinweis_kein_f_dann_absuchen(self):
        f, blicke = 0, []
        for schritt in range(80):
            self.uhr.t = schritt * 0.1
            befehle = self.pilot.tick(info(ziel=(0, 0.05)))
            f += befehle.count(('tippen', 'f'))
            blicke += self.blicke(befehle)
            if self.pilot.modus == 'Umgebung absuchen':
                break
        self.assertEqual(f, 0)  # früher blind F – öffnete fremde Domänen-Eingänge
        self.assertEqual(self.pilot.modus, 'Umgebung absuchen')
        self.assertTrue(blicke and blicke[0][1] > 0)  # dreht zur ersten Suchrichtung (+90°)
        # Sobald die Kamera dort ist, läuft er los.
        self.uhr.t += 0.5
        self.assertIn(('halten', 'w'), self.pilot.tick(info(ziel=(0, 0.05), kegel=self.pilot.such_kurs)))

    def test_am_ziel_mit_npc_hinweis_hoechstens_drei_mal_f(self):
        f = 0
        for schritt in range(80):
            self.uhr.t = schritt * 0.1
            befehle = self.pilot.tick(info(ziel=(0, 0.05), f_hinweis={'y': 0.5, 'gespraech': True}))
            f += befehle.count(('tippen', 'f'))
        self.assertEqual(f, 3)

    def test_npc_unterwegs_nicht_ansprechen(self):
        self.uhr.t = 100
        befehle = self.pilot.tick(info(ziel=(0, 1.0), f_hinweis={'y': 0.5, 'gespraech': True}))
        self.assertNotIn(('tippen', 'f'), befehle)

    def test_truhe_unterwegs_oeffnen(self):
        self.uhr.t = 100
        befehle = self.pilot.tick(info(ziel=(0, 1.0), f_hinweis={'y': 0.5, 'gespraech': False}))
        self.assertIn(('tippen', 'f'), befehle)

    def test_gleiten_einmal_pro_fall(self):
        leer = 0
        for schritt in range(20):
            self.uhr.t = 100 + schritt * 0.1
            leer += self.pilot.tick(info(ziel=(0, 1.0), faellt=True)).count(('tippen', 'space'))
        self.assertEqual(leer, 1)  # zweites Leer würde den Gleiter wieder schließen
        self.uhr.t = 103
        self.pilot.tick(info(ziel=(0, 1.0), faellt=False))
        self.uhr.t = 104
        self.pilot.tick(info(ziel=(0, 1.0), faellt=False))  # stabile Landung statt eines Fehlbilds
        self.uhr.t = 108
        self.assertIn(('tippen', 'space'), self.pilot.tick(info(ziel=(0, 1.0), faellt=True)))

    def test_teleport_bei_fernem_ziel(self):
        self.pilot.teleport_erlaubt = True
        befehle = []
        for schritt in range(120):
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(90, 1.0), kegel=90.0))
        self.assertEqual(befehle.count(('teleport',)), 1)  # nach 8 s am Kartenrand, dann 3 min Pause

    def test_kein_teleport_wenn_ausgeschaltet_oder_nah(self):
        befehle = []
        for schritt in range(120):
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(90, 1.0), kegel=90.0))
        self.pilot.teleport_erlaubt = True
        for schritt in range(120):
            self.uhr.t = 200 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(90, 0.6), kegel=90.0))
        self.assertNotIn(('teleport',), befehle)

    def test_klettern_kurz_dann_absteigen_und_umgehen(self):
        befehle = []
        for schritt in range(80):
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(200, 0.97), klettert=True, bewegt=False))
        self.assertNotIn(('tippen', 'space'), befehle)  # Leertaste = Kletter-Sprung nach oben
        self.assertIn(('tippen', 'x'), befehle)          # nach 6 s absteigen …
        self.assertTrue(self.blicke(befehle))            # … und seitlich umgehen
        self.assertEqual(befehle.count(('tippen', 'x')), 1)

    def test_teleport_wird_beim_klettern_nicht_unterdrueckt(self):
        self.pilot.teleport_erlaubt = True
        befehle = []
        for schritt in range(120):
            self.uhr.t = 100 + schritt * .1
            neu = self.pilot.tick(info(ziel=(333, .94), klettert=True, bewegt=False))
            if ('teleport',) in neu:
                self.assertIn(('loslassen', 'w'), neu)
                self.assertLess(neu.index(('loslassen', 'w')), neu.index(('teleport',)))
            befehle += neu
        self.assertEqual(befehle.count(('teleport',)), 1)

    def test_nahes_ziel_unterbricht_teleport_wartezeit(self):
        self.pilot.teleport_erlaubt = True
        self.uhr.t = 100
        self.pilot.tick(info(ziel=(333, .94)))
        self.uhr.t = 107
        self.pilot.tick(info(ziel=(333, .5), klettert=True))
        self.uhr.t = 110
        self.assertNotIn(('teleport',), self.pilot.tick(info(ziel=(333, .94))))

    def test_nach_drei_umwegen_laenger_klettern(self):
        self.pilot.kletter_versuche = 3
        befehle = []
        for schritt in range(150):  # 15 s an der Wand
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(200, 0.5), klettert=True))
        self.assertNotIn(('tippen', 'x'), befehle)

    def test_zu_den_rand_pfeilen_drehen(self):
        befehle = self.pilot.tick(info(ziel=(0, 0.05), pfeile=[(0.67, 0.18), (0.75, 0.33)]))
        self.assertTrue(self.pilot.modus.startswith(('kampf (dreht zum Gegnerpfeil', 'kampf (ausweichen)')))
        self.assertTrue(self.blicke(befehle)[0][1] > 0)  # nach rechts
        self.assertNotIn(('tippen', 'f'), befehle)

    def test_kampfbereitschaft_nach_balken(self):
        self.uhr.t = 100
        self.pilot.tick(info(ziel=(0, 0.05), gegner=(0.5, 0.3, 0.05)))
        self.uhr.t = 102  # Gegner springt an, Balken außerhalb des Bildes
        befehle = self.pilot.tick(info(ziel=(0, 0.05)))
        self.assertEqual(self.pilot.modus, 'kampf (sucht Gegner)')
        self.assertNotIn(('klick',), befehle)  # verlorenes Ziel erst wiederfinden
        self.uhr.t = 105  # 5 s nichts mehr: zurück zum Questziel
        self.pilot.tick(info(ziel=(0, 0.05)))
        self.assertNotIn('kampf', self.pilot.modus)

    def test_herausforderung_haelt_im_kampf(self):
        befehle = []
        for schritt in range(100):
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(90, 0.97), herausforderung=True))
        self.assertEqual(self.pilot.modus, 'kampf (sucht Gegner)')
        self.assertNotIn(('teleport',), befehle)       # nicht weglaufen oder teleportieren
        self.assertTrue(self.blicke(befehle))          # umsehen
        self.assertNotIn(('klick',), befehle)  # Herausforderung allein erlaubt keinen Blindangriff

    def test_antwortoption_mit_f_waehlen(self):
        befehle = []
        for schritt in range(20):
            self.uhr.t = schritt * 0.1
            befehle += self.pilot.tick(info(hud=False, dialog=True, dialog_option=0.744))
        tasten = [b[1] for b in befehle if b[0] == 'tippen']
        self.assertTrue(tasten)
        self.assertEqual(set(tasten), {'f'})  # keine Leertaste bei Antworten
        self.assertEqual(self.pilot.modus, 'dialog (Antwort)')

    def test_nach_dialogende_kein_f_mehr(self):
        self.pilot.tick(info(hud=False, dialog=True))
        befehle = []
        for schritt in range(1, 14):  # 1,3 s Nachlauf, Dialog schon weg, NPC daneben
            self.uhr.t = schritt * 0.1
            befehle += self.pilot.tick(info(hud=False, dialog=False))
        self.assertFalse([b for b in befehle if b[0] == 'tippen'])

    def test_sichtbare_spur_auch_ohne_festhaengen(self):
        # Bestätigte V-Spur hat Vorrang vor der Luftlinie zum Questmarker.
        self.pilot.tick(info(ziel=(0, 1.0), kegel=0.0, spur=(0.2, 0.4), spur_frisch=True))
        self.assertEqual(self.pilot.modus, 'folgt V-Spur')
        # Nach dem Festhängen: der Spur folgen, die um das Hindernis führt.
        self.pilot.befreiungen = 1
        self.uhr.t = 1
        befehle = self.pilot.tick(info(ziel=(0, 1.0), kegel=0.0, spur=(0.2, 0.4), spur_frisch=True))
        self.assertEqual(self.pilot.modus, 'folgt V-Spur')
        self.assertTrue(self.blicke(befehle)[0][1] < 0)  # Spur links, obwohl Ziel geradeaus
        self.assertIn('w', self.pilot.gehalten)

    def test_festgesteckt_ohne_spur_selten_v(self):
        befehle = []
        for schritt in range(700):  # 70 s lang festgesteckt
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(0, 1.0), kegel=0.0, bewegt=False))
        self.assertGreaterEqual(befehle.count(('tippen', 'v')), 1)
        self.assertLessEqual(befehle.count(('tippen', 'v')), 4)  # höchstens alle 20 Sekunden

    def test_v_spur_frueh_und_mit_abstand_anfordern(self):
        befehle = []
        for schritt in range(400):
            self.uhr.t = 100 + schritt * 0.1
            befehle += self.pilot.tick(info(ziel=(0, 1.0), kegel=0.0))
        self.assertEqual(befehle.count(('tippen', 'v')), 2)

    def test_dialog_wartet_bis_gelesen(self):
        befehle = self.pilot.tick(info(hud=False, dialog=True, dialog_bereit=False))
        self.assertFalse([b for b in befehle if b[0] == 'tippen'])
        self.assertEqual(self.pilot.modus, 'dialog (liest mit)')
        self.uhr.t = 1
        befehle = self.pilot.tick(info(hud=False, dialog=True, dialog_bereit=True))
        self.assertTrue([b for b in befehle if b[0] == 'tippen'])

    def test_element_aus_mitgelesenem_dialog(self):
        self.pilot.team = {2: 'pyro', 3: 'hydro'}
        befehle = self.pilot._element_angriff({'stichworte': ['hydro'], 'state': 'Pyro torch'})
        self.assertIn(('tippen', '3'), befehle)

    def test_absuchen_folgt_ki_hinweis(self):
        hinweis = {'scene': 'exploration', 'ziel_kurs': 300.0, 'alter': 3}
        for schritt in range(80):
            self.uhr.t = schritt * 0.1
            self.pilot.tick(info(ziel=(0, 0.05)), hinweis)
        self.assertEqual(self.pilot.such_kurs, 300.0)

    def test_unterwegs_weit_weg_kein_f(self):
        self.uhr.t = 100
        self.assertNotIn(('tippen', 'f'), self.pilot.tick(info(ziel=(0, 1.0))))

    def test_menue_mit_x_wird_mit_esc_geschlossen(self):
        self.pilot.tick(info(ziel=(0, 1.0)))
        befehle = self.pilot.tick(info(hud=False, menue_x=True))
        self.assertIn(('loslassen', 'w'), befehle)
        self.assertNotIn(('tippen', 'escape'), befehle)
        self.uhr.t = 1.9
        self.assertNotIn(('tippen', 'escape'), self.pilot.tick(info(hud=False, menue_x=True)))
        self.uhr.t = 2.1
        self.assertIn(('tippen', 'escape'), self.pilot.tick(info(hud=False, menue_x=True)))

    def test_zwischensequenz_ohne_x_kein_esc(self):
        befehle = []
        for schritt in range(300):
            self.uhr.t = schritt * 0.1
            befehle += self.pilot.tick(info(hud=False, menue_x=False))
        self.assertNotIn(('tippen', 'escape'), befehle)
        self.assertEqual(self.pilot.modus, 'Zwischensequenz')

    def test_story_dialoge_hintereinander_keine_schleife(self):
        self.uhr.t = 100
        self.pilot.tick(info(hud=False, dialog=True))
        self.uhr.t = 105
        self.pilot.tick(info(hud=False))                 # Zwischensequenz
        self.uhr.t = 108
        self.pilot.tick(info(hud=False, dialog=True))    # nächster Story-Dialog, ohne eigenes F
        self.uhr.t = 112
        self.pilot.tick(info(ziel=(0, 1.0)))
        self.assertNotEqual(self.pilot.modus, 'weg vom NPC')
        # Danach 20 s kein F, damit der Domänen-Eingang nicht gleich wieder aufgeht.
        self.uhr.t = 5
        self.assertNotIn(('tippen', 'f'), self.pilot.tick(info(ziel=(0, 0.05))))

    def test_ladebild_keine_eingaben(self):
        self.assertEqual(self.pilot.tick(info(hud=False, laden=True)), [])

    def test_dialog_klickt_weiter(self):
        self.pilot.tick(info(ziel=(0, 1.0)))
        befehle = self.pilot.tick(info(hud=False, dialog=True))
        self.assertIn(('loslassen', 'w'), befehle)
        self.assertTrue(any(b[0] == 'tippen' and b[1] in ('f', 'space') for b in befehle))

    def test_endlosgespraech_dreht_weg(self):
        self.uhr.t = 100
        self.pilot.tick(info(hud=False, dialog=True))
        self.uhr.t = 105
        self.pilot.tick(info(ziel=(0, 1.0)))
        self.pilot.zuletzt['interagieren'] = 107        # er selbst hat wieder F gedrückt …
        self.uhr.t = 108
        self.pilot.tick(info(hud=False, dialog=True))  # … und gleich wieder angesprochen
        self.uhr.t = 112
        befehle = self.pilot.tick(info(ziel=(0, 1.0)))
        self.assertEqual(self.pilot.modus, 'weg vom NPC')
        self.assertTrue(self.blicke(befehle))
        self.uhr.t = 140
        self.assertNotIn(('tippen', 'f'), self.pilot.tick(info(ziel=(0, 0.05))))

    def test_domaene_folgt_ki_ziel(self):
        hinweis = {'scene': 'exploration', 'ziel_kurs': 90.0, 'alter': 4}
        befehle = self.pilot.tick(info(kegel=0.0), hinweis)
        self.assertEqual(self.pilot.modus, 'KI-Ziel')
        self.assertTrue(self.blicke(befehle)[0][1] > 0)

    def test_domaene_ohne_hinweis_erkunden(self):
        befehle = self.pilot.tick(info())
        self.assertEqual(self.pilot.modus, 'erkunden')
        self.assertIn(('halten', 'w'), befehle)

    def test_alter_ki_hinweis_wird_ignoriert(self):
        self.pilot.tick(info(), {'scene': 'exploration', 'ziel_kurs': 90.0, 'alter': 20})
        self.assertEqual(self.pilot.modus, 'erkunden')

    def test_kampf(self):
        self.uhr.t = 101
        self.pilot.zuletzt['wechsel'] = 101
        self.pilot.kampf_bis = 102  # Kampf läuft schon (zu Beginn käme erst E)
        befehle = self.pilot.tick(info(gegner=(.97, .3, 10)))
        self.assertEqual(self.pilot.modus, 'kampf (ausrichten)')
        self.assertTrue(self.blicke(befehle)[0][1] > 0)
    def test_ki_kampf_ohne_gegner_bestaetigung_ignoriert(self):
        self.pilot.tick(info(), {'scene': 'combat', 'enemy_visible': False})
        self.assertNotEqual(self.pilot.modus, 'kampf')

    def test_ki_kampf_ohne_lebensbalken_ignoriert(self):
        # Gemma erfand im Live-Lauf ständig Kämpfe („Ruin Guard mit Diluc“).
        self.pilot.tick(info(), {'scene': 'combat', 'enemy_visible': True})
        self.assertNotEqual(self.pilot.modus, 'kampf')

    def test_kampf_wechselt_reihum_ohne_fuenften_slot(self):
        tasten = set()
        for schritt in range(200):
            self.uhr.t = schritt * 0.1
            tasten |= {b[1] for b in self.pilot.tick(info(gegner=(0.5, 0.3, 0.08), q_bereit=True))
                       if b[0] == 'tippen'}
        self.assertTrue({'2', '3', '4'} <= tasten)
        self.assertNotIn('5', tasten)
        self.assertTrue({'e', 'q'} <= tasten)
    def test_zur_raute_lenken_und_laufen(self):
        befehle = self.pilot.tick(info(raute=(0.8, 0.4, 0.9)))
        self.assertEqual(self.pilot.modus, 'zur Raute')
        self.assertTrue(self.blicke(befehle)[0][1] > 0)
        self.assertIn(('halten', 'w'), befehle)  # sichtbare Raute: lenken und dabei laufen

    def test_raute_im_weg_element_angriff(self):
        self.pilot.team = {1: 'anemo', 2: 'pyro', 3: 'hydro'}
        befehle = []
        for schritt in range(40):
            self.uhr.t = schritt * 0.1
            befehle += self.pilot.tick(info(raute=(0.5, 0.4, 0.9), bewegt=False))
        self.assertIn(('tippen', '2'), befehle)  # Pyro-Figur
        self.assertIn(('tippen', 'e'), befehle)
        self.assertIn(('klick',), befehle)

    def test_element_aus_ki_text(self):
        self.pilot.team = {2: 'pyro', 3: 'hydro'}
        befehle = self.pilot._element_angriff({'state': 'A Hydro mechanism blocks the door'})
        self.assertIn(('tippen', '3'), befehle)

    def test_lenkung_lernt_robust(self):
        self.pilot.zaehler_pro_grad = 11.0
        for gemessen in (10.5, 11.5, 11.0, 2.0, 44.0):  # zwei Ausreißer
            self.pilot.drehung = (0.0, 0.0, 300)
            self.uhr.t = 0.5
            self.pilot._kalibrieren(info(kegel=300 / gemessen), self.uhr.t)
        self.assertAlmostEqual(self.pilot.zaehler_pro_grad, 11.0, delta=0.6)

    def test_festhaengen_startet_umweg_statt_blindem_sprung(self):
        for schritt in range(40):
            self.uhr.t = schritt * 0.1
            befehle = self.pilot.tick(info(ziel=(0, 1.0), bewegt=False))
            if self.pilot.umweg is not None:
                break
        self.assertIsNotNone(self.pilot.umweg)
        self.assertNotIn(('tippen', 'space'), befehle)
        self.assertTrue(self.blicke(befehle))


class TeleportAblauf(unittest.TestCase):
    def setUp(self):
        self.instance = object.__new__(app.App)
        self.instance.messages = queue.Queue()
        self.instance.command = Mock(return_value=True)
        self.instance.close_menus = Mock(return_value=False)
        self.instance.save_diag = Mock()

    def test_reales_pardis_bild_fuehrt_zur_teleportauswahl(self):
        look = Mock(side_effect=[bild('karte_pardis_oben')] + [bild('karte')] * 4 + [bild('karte_teleport_fenster')])
        self.assertTrue(self.instance.teleport(look, 'spiel'))
        befehle = [c.args[0] for c in self.instance.command.call_args_list]
        self.assertTrue(any(b[0] == 'maus_klick' for b in befehle))
        self.assertIn(('tippen', 'f', .08), befehle)
        self.instance.close_menus.assert_not_called()

    def test_stop_vor_bestaetigung_meldet_keinen_erfolg(self):
        self.instance.command.side_effect = lambda b, t: b != ('tippen', 'f', .08)
        look = Mock(side_effect=[bild('karte_pardis_oben')] + [bild('karte')] * 4 + [bild('karte_teleport_fenster')])
        self.assertFalse(self.instance.teleport(look, 'spiel'))

    def test_langsames_einblenden_bekommt_frisches_bild(self):
        # Nach der Karte: Heranzoomen (3 Stufen), weil der nächste Wegpunkt weit vom Ziel liegt.
        look = Mock(side_effect=[bild('ladebild'), bild('karte_pardis_oben')] + [bild('karte')] * 4
                    + [bild('karte_teleport_fenster')])
        self.assertTrue(self.instance.teleport(look, 'spiel'))
        self.assertEqual(look.call_count, 7)

    def test_fehlendes_ziel_bricht_begrenzt_ohne_teleport_ab(self):
        look = Mock(return_value=bild('karte_quest_fenster'))
        with patch.object(reflexe, 'raute', return_value=None):
            self.assertFalse(self.instance.teleport(look, 'spiel'))
        self.assertEqual(look.call_count, 28)  # Start + 3 Zoomstufen + 24 Nachbarfelder
        self.assertEqual(self.instance.save_diag.call_args.args[1]['modus'], 'Teleport: Questsymbol fehlt')
        self.instance.close_menus.assert_called_once()
        self.assertFalse(any(c.args[0][0] == 'maus_klick'
                             or c.args[0] == ('tippen', 'f', .08)
                             for c in self.instance.command.call_args_list))


class Parallelbetrieb(unittest.TestCase):
    def test_koerper_laeuft_waehrend_ki_rechnet(self):
        """Die langsame KI darf die Reflexschleife nicht blockieren."""
        instance = object.__new__(app.App)
        instance.stop = threading.Event()
        instance.messages = queue.Queue()
        instance.running = True
        instance.stop_reason = ''
        instance.bridge_active = False
        instance.team = {}
        ki_laeuft = threading.Event()

        def langsame_ki(*_):
            ki_laeuft.set()
            instance.stop.wait(5)
            raise app.InvalidDecision('abgebrochen')

        feld = bild('oberwelt_nacht')
        shot = Mock(width=feld.shape[1], height=feld.shape[0], rgb=feld.tobytes())
        screen = Mock()
        screen.grab.return_value = shot
        context = Mock(__enter__=Mock(return_value=screen), __exit__=Mock(return_value=False))
        befehle = []

        def merken(order, target):
            befehle.append(order)
            if len(befehle) > 3 and ki_laeuft.is_set():
                instance.stop.set()
            return True

        with patch.object(app.mss, 'mss', return_value=context), \
                patch.object(app, 'window', return_value=(1, {})), \
                patch.object(app.win_input, 'ensure_permissions'), \
                patch.object(app, 'ki_hinweis', side_effect=langsame_ki), \
                patch.object(instance, 'save_diag'), \
                patch.object(instance, 'command', side_effect=merken), \
                patch.object(instance.stop, 'wait') as warten:
            warten.side_effect = lambda s=None: threading.Event.wait(instance.stop, min(s or 0, 0.01))
            instance.autopilot('gemma3:4b', 'test', False, 'gold', 600)
        self.assertTrue(ki_laeuft.is_set())
        self.assertIn(('halten', 'w'), befehle)
        self.assertFalse(instance.running)


if __name__ == '__main__':
    unittest.main()
