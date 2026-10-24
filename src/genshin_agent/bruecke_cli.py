"""Claudes Seite der Brücke zum Genshin-Panel (Claude-Steuerung, F11).

  python bruecke_cli.py status              Zustand und Pfad des aktuellen Spielbilds
  python bruecke_cli.py senden '<JSON>'     Befehle senden, auf Ausführung + frisches Bild warten
  python bruecke_cli.py hilfe               Befehlsliste

Das Panel führt nur geprüfte Befehle aus (fertigkeiten.py), nur ins Genshin-Fenster und
nur, solange es im Vordergrund ist. Dateien: logs/bruecke/{zustand.json, bild.jpg, befehl_N.json}.
"""
import json
from pathlib import Path
import sys
import time

ORDNER = Path(__file__).resolve().parent / 'logs' / 'bruecke'


def zustand():
    for versuch in range(5):
        try:
            return json.loads((ORDNER / 'zustand.json').read_text(encoding='utf-8'))
        except PermissionError:  # Panel ersetzt die Datei gerade
            time.sleep(0.05)
        except (OSError, ValueError):
            return None
    return None


def ausgeben(daten):
    alter = time.time() - daten.get('zeit', 0)
    print(json.dumps(daten, ensure_ascii=False, indent=1))
    print(f'Bild: {ORDNER / "bild.jpg"}   (Zustand {alter:.1f} s alt'
          + (', Spiel NICHT im Vordergrund' if not daten.get('spiel_aktiv') else '') + ')')


def senden(befehle, wartezeit=90):
    if isinstance(befehle, dict):
        befehle = [befehle]
    ORDNER.mkdir(parents=True, exist_ok=True)
    jetzt = zustand()
    offen = [int(p.stem.split('_', 1)[1]) for p in ORDNER.glob('befehl_*.json') if p.stem.split('_', 1)[1].isdigit()]
    nr = max([jetzt['nr'] if jetzt else 0] + offen) + 1
    vorlaeufig = ORDNER / f'.befehl_{nr}.tmp'
    vorlaeufig.write_text(json.dumps({'befehle': befehle}, ensure_ascii=False), encoding='utf-8')
    ziel = ORDNER / f'befehl_{nr}.json'
    vorlaeufig.replace(ziel)
    ende = time.time() + wartezeit
    while time.time() < ende:
        daten = zustand()
        if daten and daten.get('nr', 0) >= nr and daten.get('bild_nach_nr', 0) >= nr:
            ausgeben(daten)
            return 0 if (daten.get('ergebnis') or {}).get('ok') else 1
        time.sleep(0.3)
    ziel.unlink(missing_ok=True)  # nie verspätet ausführen lassen
    print(f'Keine Antwort auf Befehl {nr}: Läuft der Autopilot (F8) mit Claude-Steuerung (F11) '
          'und ist Genshin im Vordergrund?')
    daten = zustand()
    if daten:
        ausgeben(daten)
    return 2


def main(argumente):
    if len(argumente) < 2 or argumente[1] not in ('status', 'senden', 'hilfe'):
        print(__doc__)
        return 2
    if argumente[1] == 'hilfe':
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fertigkeiten
        print(fertigkeiten.HILFE)
        return 0
    if argumente[1] == 'status':
        daten = zustand()
        if not daten:
            print('Noch kein Zustand: Autopilot mit Claude-Steuerung (F11) starten.')
            return 2
        ausgeben(daten)
        return 0
    if len(argumente) < 3:
        print("senden braucht JSON, z. B. '[{\"tun\":\"interagieren\"}]'")
        return 2
    return senden(json.loads(argumente[2]))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
