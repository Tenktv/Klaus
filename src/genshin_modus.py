"""Klaus-Anbindung: Spielpanel öffnen, Status lesen, laufende Sitzung stoppen.

Das Werkzeug selbst startet keine Eingaben. F8/Start im eigenen Panel eröffnet
eine auf zehn Minuten begrenzte Sitzung ausschließlich für GenshinImpact.exe.
"""
from pathlib import Path
import subprocess
import sys
import threading

ORDNER = Path(__file__).resolve().parent / 'genshin_agent'
_prozess = None
_lock = threading.Lock()


def oeffnen():
    global _prozess
    import pc_zugriff
    pc_zugriff._pruefe_frei()
    with _lock:
        if _prozess is not None and _prozess.poll() is None:
            return 'Genshin-Panel ist bereits geöffnet. F8 startet, F9 stoppt.'
        python = Path(sys.executable)
        pythonw = python.with_name('pythonw.exe')
        if pythonw.exists():
            python = pythonw
        _prozess = subprocess.Popen([str(python), str(ORDNER / 'app.py')],
                                    cwd=str(ORDNER), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return 'Genshin-Panel geöffnet. Erst Bewegungstest, danach F8 für maximal zehn Minuten. F9 stoppt.'


def stoppen():
    (ORDNER / 'stop.request').touch()
    return 'Stopp an den Genshin-Modus gesendet. Laufende KI-Antworten werden verworfen.'


def status():
    logfile = ORDNER / 'logs' / 'runtime.log'
    if not logfile.exists():
        return 'Noch kein Genshin-Test protokolliert.'
    with logfile.open('rb') as source:
        source.seek(0, 2)
        source.seek(max(0, source.tell()-4000))
        lines = source.read().decode('utf-8', errors='replace').splitlines()
    return '\n'.join(lines[-5:])


def werkzeug(aktion='status'):
    if aktion in ('start', 'oeffnen'):
        return oeffnen()
    if aktion == 'stop':
        return stoppen()
    if aktion == 'status':
        return status()
    return 'Erlaubt: oeffnen, stop, status.'
