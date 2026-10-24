"""Rätsel und Truhen aus der öffentlichen HoYoLAB-Webkarte, lokal gespeichert.

Datei: vorlagen/raetsel_atlas.json (laden mit werkzeuge/raetsel_atlas_laden.py). Je Punkt: Art
(raetsel/truhe), Typ (z. B. „Torch Puzzle“, „Seelie“, „Precious Chest“), Atlas-Koordinaten wie
kartenatlas.json und bei Rätseln der Community-Hinweis plus Adresse eines Fundort-Bildes.
Hinweise sind kurze Notizen („Torches are on left, right and behind chest.“), keine
Komplettlösungen – sie geben Claude (F11) den Kontext, welches Rätsel hier steht und was zu tun ist.
"""
from functools import lru_cache
import json
import math
from pathlib import Path

DATEI = Path(__file__).with_name('vorlagen') / 'raetsel_atlas.json'
ATLAS = Path(__file__).with_name('vorlagen') / 'kartenatlas.json'
# Aus dem Teleport-Atlas: freischaltbare Orte (Wegpunkt/Domäne durch Annähern, Statue per F).
ATLAS_ARTEN = {3: ('teleport', 'Teleport Waypoint'), 2: ('statue', 'Statue of The Seven'), 154: ('domaene', 'Domain')}


@lru_cache(maxsize=1)
def punkte():
    liste = []
    if DATEI.exists():
        daten = json.loads(DATEI.read_text(encoding='utf-8'))
        liste += [dict(p, id=int(i)) for i, p in daten['punkte'].items()]
    if ATLAS.exists():
        for p in json.loads(ATLAS.read_text(encoding='utf-8-sig'))['data']['point_list']:
            if p['label_id'] in ATLAS_ARTEN:
                art, typ = ATLAS_ARTEN[p['label_id']]
                liste.append({'id': p['id'], 'art': art, 'typ': typ, 'label_id': p['label_id'], 'x_pos': p['x_pos'],
                              'y_pos': p['y_pos'], 'area_id': p.get('area_id'), 'z_level': p.get('z_level', 0)})
    return tuple(liste)


def in_der_naehe(x_pos, y_pos, radius=300, anzahl=6, art=None):
    """Nächste Punkte um eine Atlasposition, nach Abstand sortiert (Abstand in Atlaseinheiten)."""
    treffer = []
    for p in punkte():
        if art is not None and p['art'] != art:
            continue
        abstand = math.hypot(p['x_pos'] - x_pos, p['y_pos'] - y_pos)
        if abstand <= radius:
            treffer.append(dict(p, abstand=round(abstand)))
    return sorted(treffer, key=lambda p: p['abstand'])[:anzahl]


def atlas_position(transform, x, y, breite, hoehe):
    """Relativer Bildpunkt einer registrierten Weltkarte (kartenatlas.lokalisieren) -> Atlas."""
    return ((x * breite - transform['offset_x']) / transform['scale'],
            (y * hoehe - transform['offset_y']) / (transform['scale'] * transform['y_sign']))


def kurz(punkte_liste):
    """Für Brücke und Protokoll: Typ, Abstand, Hinweis, Bildadresse."""
    return [{'art': p['art'], 'typ': p['typ'], 'abstand': p['abstand'],
             'hinweis': p.get('hinweis', ''), 'bild': p.get('bild', '')} for p in punkte_liste]
