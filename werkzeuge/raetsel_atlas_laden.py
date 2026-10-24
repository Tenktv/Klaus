"""Rätsel- und Truhenpunkte der öffentlichen HoYoLAB-Webkarte einmal lokal speichern.

Positionen (zwei Listenabfragen) plus je Rätselpunkt der Community-Hinweis („content“) und das
Fundort-Bild („img“, nur die Adresse). Gedrosselt (3 Abfragen/s) und fortsetzbar: bereits
geladene Punkte werden übersprungen. Kein Login, keine Spielbilder werden übertragen.

Aufruf:  .venv/Scripts/python.exe werkzeuge/raetsel_atlas_laden.py
"""
import json
from pathlib import Path
import time
import urllib.request

BASIS = 'https://sg-public-api-static.hoyolab.com/common/map_user/ys_obc'
PARAM = 'map_id=2&app_sn=ys_obc&lang=en-us'
ZIEL = Path(__file__).resolve().parents[1] / 'src' / 'genshin_agent' / 'vorlagen' / 'raetsel_atlas.json'
KATEGORIEN = {186: 'raetsel', 13: 'truhe', 4: 'sammeln'}
# Aus „Special Items“ nur die Okuli (an den Statuen abzugeben).
OKULI = {5, 6, 194, 403, 508, 626, 694, 833}


def holen(pfad):
    with urllib.request.urlopen(f'{BASIS}/{pfad}', timeout=30) as antwort:
        daten = json.load(antwort)
    if daten.get('retcode') != 0:
        raise RuntimeError(f'{pfad}: {daten.get("message")}')
    return daten['data']


def main():
    atlas = json.loads(ZIEL.read_text(encoding='utf-8')) if ZIEL.exists() else {'punkte': {}}
    baum = holen(f'v2/map/label/tree?{PARAM}')['tree']
    namen = {kind['id']: kind['name'] for oben in baum for kind in (oben.get('children') or [])}
    for oben, art in KATEGORIEN.items():
        for p in holen(f'v3/map/point/list?{PARAM}&label_ids={oben}')['point_list']:
            if art == 'sammeln' and p['label_id'] not in OKULI:
                continue
            eintrag = atlas['punkte'].setdefault(str(p['id']), {})
            eintrag.update(art=art, label_id=p['label_id'], typ=namen.get(p['label_id'], '?'),
                           x_pos=p['x_pos'], y_pos=p['y_pos'], area_id=p['area_id'], z_level=p['z_level'])
    atlas.update(quelle=f'{BASIS}/v3/map/point/list?{PARAM}', stand=time.strftime('%Y-%m-%d'),
                 koordinaten='wie kartenatlas.json (HoYoLAB CRS.Simple, x_pos/y_pos)')
    offen = [i for i, e in atlas['punkte'].items() if e['art'] in ('raetsel', 'sammeln') and 'hinweis' not in e]
    print(f"{len(atlas['punkte'])} Punkte, davon {len(offen)} Rätsel ohne Hinweis – lade Details …")
    for n, punkt_id in enumerate(offen, 1):
        try:
            info = holen(f'v1/map/point/info?{PARAM}&point_id={punkt_id}')['info']
        except (OSError, RuntimeError, ValueError) as fehler:
            print(f'  {punkt_id}: {fehler}')
            time.sleep(2)
            continue
        atlas['punkte'][punkt_id].update(hinweis=(info.get('content') or '').strip(), bild=info.get('img') or '')
        if n % 100 == 0 or n == len(offen):
            ZIEL.write_text(json.dumps(atlas, ensure_ascii=False), encoding='utf-8')
            print(f'  {n}/{len(offen)}')
        time.sleep(1 / 3)
    ZIEL.write_text(json.dumps(atlas, ensure_ascii=False), encoding='utf-8')
    print('fertig:', ZIEL)


if __name__ == '__main__':
    main()
