"""Rätsel-Werkzeuge: hohe Befehle (hingehen, angreifen, gleiten …) → Grundbefehle der App.

Wird von der Claude-Brücke genutzt. Nur erlaubte Tasten, begrenzte Zeiten, Winkel und
Wiederholungen. Grundbefehle: ('tippen', taste, s) / ('halten', taste) / ('loslassen', taste) /
('blick', dx, dy) / ('klick',) / ('maus_halten', s) / ('warten', s).
"""
import math

from reflexe import bildwinkel

VFOV = 45.0  # vertikales Sichtfeld der Spielkamera
TASTEN = {'w', 'a', 's', 'd', 'f', 'r', 'x', 'space', 'shift', 'e', 'q', 'escape', '1', '2', '3', '4', '5'}
ELEMENTE = {'anemo', 'pyro', 'hydro', 'electro', 'cryo', 'geo', 'dendro'}
RICHTUNGEN = {'vor': 'w', 'zurueck': 's', 'links': 'a', 'rechts': 'd'}
ARTEN = {'normal', 'geladen', 'e', 'e_halten', 'q', 'zielschuss'}
MAX_BEFEHLE = 8

HILFE = '''Befehle (Liste von Objekten, höchstens 8 pro Sendung):
{"tun":"drehen","grad":45}                 Kamera nach rechts (+) / links (-)
{"tun":"nicken","grad":10}                 Kamera nach unten (+) / oben (-)
{"tun":"zielen","x":0.3,"y":0.5}           Bildpunkt (0..1) in die Bildmitte holen
{"tun":"laufen","sekunden":2,"richtung":"vor|zurueck|links|rechts","sprint":false}
{"tun":"hingehen","x":0.3,"sekunden":2}    zur Bildposition x drehen und laufen
{"tun":"interagieren"}                     F
{"tun":"springen"}   {"tun":"gleiten","sekunden":3}
{"tun":"figur","slot":2}                   Figur wechseln (1-5)
{"tun":"angreifen","x":0.5,"y":0.4,"art":"normal|geladen|e|e_halten|q|zielschuss","anzahl":3,"element":"pyro"}
{"tun":"taste","taste":"r","sekunden":0.1} {"tun":"warten","sekunden":2}'''


class Ungueltig(ValueError):
    pass


def team_lesen(text):
    """„1=anemo 2=pyro …“ → {1: 'anemo', 2: 'pyro', …}; Unbekanntes wird übersprungen."""
    team = {}
    for teil in str(text).replace(',', ' ').split():
        slot, _, element = teil.partition('=')
        if slot.strip().isdigit() and element.strip().lower() in ELEMENTE and 1 <= int(slot) <= 5:
            team[int(slot)] = element.strip().lower()
    return team


def _zahl(befehl, name, unten, oben, standard=None):
    wert = befehl.get(name, standard)
    if isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert):
        raise Ungueltig(f'{name} muss eine Zahl sein')
    if not unten <= wert <= oben:
        raise Ungueltig(f'{name} muss zwischen {unten} und {oben} liegen')
    return float(wert)


def hoehenwinkel(y):
    """Vertikale Bildposition (0 oben .. 1 unten) als Winkel zur Bildmitte (+ = unten)."""
    return math.degrees(math.atan((y - 0.5) * 2 * math.tan(math.radians(VFOV / 2))))


def _blick(grad_x, grad_y, zaehler_pro_grad):
    return [('blick', round(grad_x * zaehler_pro_grad), round(grad_y * zaehler_pro_grad)), ('warten', 0.3)]


def _laufen(sekunden, richtung='vor', sprint=False):
    taste = RICHTUNGEN[richtung]
    if not sprint:
        return [('tippen', taste, sekunden)]
    return [('halten', taste), ('tippen', 'shift', sekunden), ('loslassen', taste)]


def uebersetzen(befehl, zaehler_pro_grad, team):
    """Einen hohen Befehl prüfen und in Grundbefehle übersetzen."""
    if not isinstance(befehl, dict):
        raise Ungueltig('Befehl muss ein Objekt sein')
    tun = befehl.get('tun')
    z = zaehler_pro_grad
    if tun == 'drehen':
        return _blick(_zahl(befehl, 'grad', -360, 360), 0, z)
    if tun == 'nicken':
        return _blick(0, _zahl(befehl, 'grad', -80, 80), z)
    if tun == 'zielen':
        x, y = _zahl(befehl, 'x', 0, 1), _zahl(befehl, 'y', 0, 1, 0.5)
        return _blick(bildwinkel(x), hoehenwinkel(y), z)
    if tun == 'laufen':
        richtung = befehl.get('richtung', 'vor')
        if richtung not in RICHTUNGEN:
            raise Ungueltig('richtung: vor, zurueck, links oder rechts')
        return _laufen(_zahl(befehl, 'sekunden', 0.1, 6), richtung, befehl.get('sprint') is True)
    if tun == 'hingehen':
        x = _zahl(befehl, 'x', 0, 1)
        return _blick(bildwinkel(x), 0, z) + _laufen(_zahl(befehl, 'sekunden', 0.1, 6, 2), 'vor',
                                                     befehl.get('sprint') is True)
    if tun == 'interagieren':
        return [('tippen', 'f', 0.08), ('warten', 0.5)]
    if tun == 'springen':
        return [('tippen', 'space', 0.08), ('warten', 0.6)]
    if tun == 'gleiten':
        # Sprung, in der Luft nochmal Leertaste = Gleitschirm; W hält die Richtung.
        dauer = _zahl(befehl, 'sekunden', 0.5, 6, 3)
        return [('halten', 'w'), ('tippen', 'space', 0.08), ('warten', 0.45), ('tippen', 'space', 0.08),
                ('warten', dauer), ('loslassen', 'w')]
    if tun == 'figur':
        return [('tippen', str(int(_zahl(befehl, 'slot', 1, 5))), 0.08), ('warten', 0.6)]
    if tun == 'angreifen':
        return _angreifen(befehl, z, team)
    if tun == 'taste':
        taste = befehl.get('taste')
        if taste not in TASTEN:
            raise Ungueltig(f'Taste nicht erlaubt: {taste}')
        return [('tippen', taste, _zahl(befehl, 'sekunden', 0.05, 3, 0.1))]
    if tun == 'warten':
        return [('warten', _zahl(befehl, 'sekunden', 0.1, 10))]
    if tun == 'klick':
        return [('klick',), ('warten', 0.25)]
    raise Ungueltig(f'Unbekannter Befehl: {tun}')


def _angreifen(befehl, z, team):
    befehle = []
    element = befehl.get('element')
    if element is not None:
        if element not in ELEMENTE:
            raise Ungueltig(f'Unbekanntes Element: {element}')
        slots = sorted(slot for slot, e in team.items() if e == element)
        if not slots:
            raise Ungueltig(f'Niemand im Team hat {element} (Team: {team})')
        befehle += [('tippen', str(slots[0]), 0.08), ('warten', 0.6)]
    if 'x' in befehl:
        befehle += _blick(bildwinkel(_zahl(befehl, 'x', 0, 1)), hoehenwinkel(_zahl(befehl, 'y', 0, 1, 0.5)), z)
    art = befehl.get('art', 'normal')
    if art not in ARTEN:
        raise Ungueltig(f'art: {", ".join(sorted(ARTEN))}')
    anzahl = int(_zahl(befehl, 'anzahl', 1, 10, 3 if art == 'normal' else 1))
    einzeln = {
        'normal': [('klick',), ('warten', 0.25)],
        'geladen': [('maus_halten', 1.2), ('warten', 0.4)],
        'e': [('tippen', 'e', 0.08), ('warten', 0.8)],
        'e_halten': [('tippen', 'e', 1.2), ('warten', 0.8)],
        'q': [('tippen', 'q', 0.08), ('warten', 1.5)],
        # Bogen: R = Zielmodus, Fadenkreuz in der Bildmitte, gehaltener Schuss.
        'zielschuss': [('tippen', 'r', 0.08), ('warten', 0.4), ('maus_halten', 1.6), ('warten', 0.4),
                       ('tippen', 'r', 0.08)],
    }[art]
    return befehle + einzeln * anzahl


def pruefen(befehle, zaehler_pro_grad, team):
    """Ganze Sendung prüfen; liefert pro Befehl die Grundbefehle (alles oder nichts)."""
    if not isinstance(befehle, list) or not 1 <= len(befehle) <= MAX_BEFEHLE:
        raise Ungueltig(f'1 bis {MAX_BEFEHLE} Befehle als Liste senden')
    return [uebersetzen(befehl, zaehler_pro_grad, team) for befehl in befehle]
