"""Lokale Kartenregistrierung gegen öffentliche HoYoLAB-Punkte.

Die Registrierung erfordert mehrere geometrisch übereinstimmende Symbole.
Atlasdaten sagen nichts über Freischaltungen des Spielaccounts aus.
"""
from functools import lru_cache
from itertools import combinations
import json
from pathlib import Path

import numpy as np

import reflexe


@lru_cache(maxsize=1)
def katalog():
    datei = Path(__file__).with_name('vorlagen') / 'kartenatlas.json'
    data = json.loads(datei.read_text(encoding='utf-8-sig'))
    return tuple(p for p in data['data']['point_list'] if p['label_id'] in (2, 3))


def _zuordnen(sichtbar, atlas, scale, offset, zeichen, toleranz):
    paarungen = []
    for art in (2, 3):
        bild_ids = np.flatnonzero(sichtbar[:, 2] == art)
        atlas_ids = np.flatnonzero(atlas[:, 2] == art)
        if not len(bild_ids):
            continue
        position = atlas[atlas_ids, :2] * (scale * np.array([1., zeichen])) + offset
        d2 = ((sichtbar[bild_ids, None, :2] - position[None, :, :]) ** 2).sum(axis=2)
        for i, j in zip(*np.where(d2 <= toleranz ** 2)):
            paarungen.append((float(d2[i, j]), int(bild_ids[i]), int(atlas_ids[j])))
    # Ein Katalogpunkt darf nicht mehrfach zur gleichen Registrierung beitragen.
    benutzt_bild, benutzt_atlas, result = set(), set(), []
    for d2, i, j in sorted(paarungen):
        if i not in benutzt_bild and j not in benutzt_atlas:
            result.append((i, j, d2))
            benutzt_bild.add(i)
            benutzt_atlas.add(j)
    return result


def registrieren(punkte, breite=960, hoehe=540, nodes=None):
    """Pixeltransform aus normalisierten Detektionen, oder None bei Mehrdeutigkeit.

    x_pixel = scale*x_atlas + offset_x
    y_pixel = scale*y_sign*y_atlas + offset_y
    """
    nodes = katalog() if nodes is None else nodes
    sichtbar = np.array([(p['x']*breite, p['y']*hoehe,
                          2 if p['art'] == 'statue' else 3)
                         for p in punkte], dtype=float).reshape(-1, 3)
    atlas = np.array([(p['x_pos'], p['y_pos'], p['label_id'])
                      for p in nodes], dtype=float).reshape(-1, 3)
    si = np.flatnonzero(sichtbar[:, 2] == 2)
    ai = np.flatnonzero(atlas[:, 2] == 2)
    if len(sichtbar) < 6 or len(si) < 2 or len(ai) < 2:
        return None
    toleranz = 5. * hoehe / 540
    kandidaten = []
    # Nordfeste Karte: Statuenpaare begrenzen Maßstab und Translation.
    for i, j in combinations(si, 2):
        db = sichtbar[j, :2] - sichtbar[i, :2]
        if np.linalg.norm(db) < 40 * hoehe / 540:
            continue
        for a, b in combinations(ai, 2):
            for start, ende in ((a, b), (b, a)):
                for zeichen in (1., -1.):
                    da = (atlas[ende, :2] - atlas[start, :2]) * [1., zeichen]
                    scale = float(np.dot(db, da) / np.dot(da, da))
                    if not .005 < scale < 3 or np.linalg.norm(db-scale*da) > 2*toleranz:
                        continue
                    offset = sichtbar[i, :2] - atlas[start, :2] * [scale, scale*zeichen]
                    matches = _zuordnen(sichtbar, atlas, scale, offset, zeichen, toleranz)
                    if len(matches) < 6 or sum(sichtbar[m[0], 2] == 2 for m in matches) < 2:
                        continue
                    # Gemeinsamer Least-Squares-Fit über alle gefundenen Symbole.
                    aa = np.array([atlas[m[1], :2]*[1., zeichen] for m in matches])
                    bb = np.array([sichtbar[m[0], :2] for m in matches])
                    ac, bc = aa-aa.mean(axis=0), bb-bb.mean(axis=0)
                    scale = float((ac*bc).sum()/(ac*ac).sum())
                    offset = bb.mean(axis=0)-scale*aa.mean(axis=0)
                    matches = _zuordnen(sichtbar, atlas, scale, offset, zeichen, toleranz)
                    if len(matches) >= 6 and sum(sichtbar[m[0], 2] == 2 for m in matches) >= 2:
                        fehler = float(np.sqrt(np.mean([m[2] for m in matches])))
                        kandidaten.append({'scale': scale, 'offset_x': float(offset[0]),
                                           'offset_y': float(offset[1]), 'y_sign': zeichen,
                                           'treffer': len(matches), 'fehler': fehler,
                                           'punkt_ids': tuple(nodes[m[1]]['id'] for m in matches)})
    if not kandidaten:
        return None
    kandidaten.sort(key=lambda k: (-k['treffer'], k['fehler']))
    bester = kandidaten[0]
    # Gleiche Zuordnung aus verschiedenen Paaren zählt nicht als Konkurrenz.
    beste_ids = set(bester['punkt_ids'])
    andere = next((k for k in kandidaten[1:]
                   if len(beste_ids.intersection(k['punkt_ids'])) < min(bester['treffer'], k['treffer']) - 1), None)
    if andere and bester['treffer'] < andere['treffer'] + 2:
        return None
    return bester


def lokalisieren(picture):
    """Nur Symbolgeometrie eines bestätigten Weltkartenbildes auswerten."""
    if not reflexe.karte_offen(picture):
        return None
    return registrieren(reflexe.teleportziele(picture), picture.shape[1], picture.shape[0])


def naechstgelegene(x, y, transform, breite=960, hoehe=540, anzahl=5):
    """Atlas-Ziele nahe normalisiertem Bildpunkt; Freischaltung stets unbekannt."""
    if transform is None:
        return []
    ziel_x = (x*breite-transform['offset_x']) / transform['scale']
    ziel_y = (y*hoehe-transform['offset_y']) / (transform['scale']*transform['y_sign'])
    return sorted((dict(p, freigeschaltet=None,
                        atlas_abstand=float(np.hypot(p['x_pos']-ziel_x, p['y_pos']-ziel_y)))
                   for p in katalog()), key=lambda p: p['atlas_abstand'])[:anzahl]


def lokalisieren_nahe(picture, spieler, schaetzung, scale, y_sign=1.0, radius=250.0):
    """Wenig erkundete Gegend (Natlan 22:55: nur 2-5 freie Symbole, Abgleich braucht 6 mit 2 Statuen):
    Mit ungefährer Position (letzte Peilung + Koppelnavigation) und bekanntem Maßstab genügt ein
    Symbol. Die Karte öffnet zentriert auf dem Spielerpfeil (spieler = relativer Bildpunkt).
    Jedes Symbol wird dem nächsten Atlaspunkt gleicher Art an seiner erwarteten Stelle zugeordnet;
    bei mehreren Treffern zählt nur die größte widerspruchsfreie Gruppe. Transform wie registrieren."""
    hoehe, breite = picture.shape[:2]
    px, py = spieler[0] * breite, spieler[1] * hoehe
    punkte = [(p['x_pos'], p['y_pos'], p['label_id'], p['id']) for p in katalog()]
    treffer = []
    for z in reflexe.teleportziele(picture):
        art = 2 if z['art'] == 'statue' else 3
        sx, sy = z['x'] * breite, z['y'] * hoehe
        ax = schaetzung[0] + (sx - px) / scale
        ay = schaetzung[1] + (sy - py) / (scale * y_sign)
        kandidaten = sorted((float(np.hypot(cx - ax, cy - ay)), cx, cy, pid) for cx, cy, lab, pid in punkte if lab == art)
        if not kandidaten:
            continue
        abstand, cx, cy, pid = kandidaten[0]
        eindeutig = len(kandidaten) < 2 or kandidaten[1][0] - abstand >= 160  # 4 Karten: 0 Fehlgriffe
        if abstand <= radius:
            treffer.append((sx, sy, cx, cy, pid, eindeutig))
    if not treffer:
        return None
    # Widerspruchsfrei: Alle Treffer müssen denselben Versatz (Bild minus Maßstab*Atlas) ergeben.
    versatz = [(sx - scale * cx, sy - scale * y_sign * cy) for sx, sy, cx, cy, _, _ in treffer]
    beste = max(range(len(treffer)), key=lambda i: sum(np.hypot(versatz[i][0] - v[0], versatz[i][1] - v[1]) < 12
                                                       for v in versatz))
    gruppe = [v for v in versatz if np.hypot(versatz[beste][0] - v[0], versatz[beste][1] - v[1]) < 12]
    # Ein einzelnes Symbol nur bei eindeutiger Zuordnung (sonst 110 m daneben möglich: Nachbar-Wegpunkt).
    if len(gruppe) == 1 and not treffer[beste][5]:
        return None
    ox = float(np.mean([v[0] for v in gruppe]))
    oy = float(np.mean([v[1] for v in gruppe]))
    fehler = float(np.mean([np.hypot(v[0] - ox, v[1] - oy) for v in gruppe]))
    return {'scale': scale, 'offset_x': ox, 'offset_y': oy, 'y_sign': y_sign, 'treffer': len(gruppe),
            'fehler': fehler, 'vorwissen': True}
