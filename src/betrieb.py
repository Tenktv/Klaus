"""Persistenter Ruhemodus und Herkunft der Sprachausgabe (keine Audio-/KI-Aufrufe)."""
import json
import threading
import time
from pathlib import Path

DATEI = Path(__file__).resolve().parent.parent / 'data' / 'betrieb.json'
_lock = threading.RLock()
_letzte = {'quelle': '', 'zeit': 0, 'gesprochen': False}
_cache = {'zeit': 0, 'ruhe': False}


def ruhe():
    with _lock:
        if time.monotonic() - _cache['zeit'] > .25:
            try:
                wert = json.loads(DATEI.read_text(encoding='utf-8')).get('ruhe', False)
                _cache['ruhe'] = wert if isinstance(wert, bool) else True
            except FileNotFoundError:
                _cache['ruhe'] = False
            except (OSError, ValueError):
                _cache['ruhe'] = True
            _cache['zeit'] = time.monotonic()
        return _cache['ruhe']


def setze_ruhe(an):
    if type(an) is not bool:
        raise ValueError('Ruhemodus braucht Ja oder Nein.')
    with _lock:
        DATEI.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATEI.with_suffix('.tmp')
        tmp.write_text(json.dumps({'ruhe': an}), encoding='utf-8')
        tmp.replace(DATEI)
        _cache.update(zeit=time.monotonic(), ruhe=an)
    return an


def erlaubt(stumm=False, quelle='antwort'):
    # Erinnerungen/automatische Abschlussmeldungen werden nur als Text zugestellt.
    return not stumm and not ruhe() and quelle not in ('kalender', 'automatisch', 'warnung')


def melden(quelle, gesprochen):
    with _lock:
        _letzte.update(quelle=quelle, zeit=time.time(), gesprochen=bool(gesprochen))


def status():
    with _lock:
        return dict(_letzte)
