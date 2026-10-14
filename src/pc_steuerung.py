"""Begrenzte Eingaben, jede mit Einmal-Freigabe und Stop-Veto. Keine GUI beim Import."""
import ctypes
import threading
import unicodedata

import freigabe
import pc_zugriff as pc

_eingabe_lock = threading.Lock()
TASTEN = frozenset(('enter', 'tab', 'esc', 'space', 'backspace', 'delete',
                    'left', 'right', 'up', 'down', 'home', 'end', 'pageup', 'pagedown'))
AKKORDE = frozenset(('ctrl+a', 'ctrl+c', 'ctrl+v', 'ctrl+x', 'ctrl+z', 'ctrl+y',
                     'ctrl+s', 'ctrl+f', 'shift+tab'))


def _gui():
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    return pyautogui


def _hotkey(gui, taste):
    """Auch bei Fail-safe keine vom Akkord gedrueckten Modifier zuruecklassen."""
    tasten = taste.split('+')
    try:
        gui.hotkey(*tasten)
    finally:
        failsafe = gui.FAILSAFE
        try:
            # Nur Loslassen darf den Fail-safe umgehen, niemals neue Tastendruecke.
            gui.FAILSAFE = False
            fehler = None
            for modifier in reversed(tasten[:-1]):
                try:
                    gui.keyUp(modifier)
                except Exception as e:
                    fehler = e
            if fehler is not None:
                raise fehler
        finally:
            gui.FAILSAFE = failsafe


def _unicode(zeichen):
    """Windows Unicode SendInput; kein Clipboard, keine gehaltenen Tasten."""
    from ctypes import wintypes as w
    class Keyboard(ctypes.Structure):
        _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                    ('time', w.DWORD), ('extra', ctypes.c_size_t)]
    class Mouse(ctypes.Structure):
        _fields_ = [('x', w.LONG), ('y', w.LONG), ('data', w.DWORD),
                    ('flags', w.DWORD), ('time', w.DWORD), ('extra', ctypes.c_size_t)]
    class Union(ctypes.Union):
        _fields_ = [('keyboard', Keyboard), ('mouse', Mouse)]
    class Input(ctypes.Structure):
        _fields_ = [('type', w.DWORD), ('payload', Union)]
    raw = zeichen.encode('utf-16-le')
    units = [int.from_bytes(raw[i:i+2], 'little') for i in range(0, len(raw), 2)]
    events = (Input * (2 * len(units)))()
    for i, unit in enumerate(units):
        for j, flags in enumerate((4, 6)):
            events[2*i+j].type = 1
            events[2*i+j].payload.keyboard = Keyboard(0, unit, flags, 0, 0)
    send = ctypes.WinDLL('user32', use_last_error=True).SendInput
    send.argtypes = (w.UINT, ctypes.POINTER(Input), ctypes.c_int)
    send.restype = w.UINT
    if send(len(events), events, ctypes.sizeof(Input)) != len(events):
        raise RuntimeError('Windows hat die Unicode-Eingabe abgelehnt.')


def _zahl(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Ganzzahl ausserhalb der erlaubten Grenzen.')
    return value


def ausfuehren(aktion, x=None, y=None, taste='', text='', schritte=None, knopf='left'):
    """Ein Aufruf = eine genehmigte Aktion; Text maximal 200 druckbare Zeichen."""
    try:
        if aktion not in ('bewegen', 'klicken', 'scrollen', 'taste', 'text'):
            raise ValueError('Unbekannte Eingabeaktion.')
        if aktion in ('bewegen', 'klicken'):
            _zahl(x, 0, 100000)
            _zahl(y, 0, 100000)
            if knopf not in ('left', 'right', 'middle'):
                raise ValueError('Unbekannter Mausknopf.')
            was = f'{aktion} ({x}, {y})' + (f' {knopf}' if aktion == 'klicken' else '')
        elif aktion == 'scrollen':
            _zahl(schritte, -10, 10)
            if not schritte:
                raise ValueError('Scroll-Schritte duerfen nicht null sein.')
            was = f'Scrollen: {schritte}'
        elif aktion == 'taste':
            if not isinstance(taste, str) or taste not in TASTEN | AKKORDE:
                raise ValueError('Taste oder Akkord nicht erlaubt.')
            was = f'Taste: {taste}'
        else:
            if not isinstance(text, str) or not 1 <= len(text) <= 200 or any(
                    unicodedata.category(c).startswith('C') for c in text):
                raise ValueError('Text muss 1–200 druckbare Unicode-Zeichen enthalten.')
            was = f'Text eingeben ({len(text)} Zeichen, Inhalt verborgen)'
        with pc.Z.lock:
            pc._pruefe_frei()
            generation = pc.Z.abbruch_generation

        def pruefen(gui):
            pc._pruefe_frei()
            if generation != pc.Z.abbruch_generation:
                raise pc.Gesperrt('Eingabe durch Stop oder Zeitablauf verworfen.')
            gui.failSafeCheck()
            width, height = gui.size()
            if aktion in ('bewegen', 'klicken'):
                if not (0 <= x < width and 0 <= y < height):
                    raise ValueError('Koordinaten ausserhalb des Hauptmonitors.')
            else:
                px, py = gui.position()
                if not (0 <= px < width and 0 <= py < height):
                    raise ValueError('Maus muss auf dem Hauptmonitor stehen.')

        def genehmigt(token):
            try:
                freigabe.pruefe(token, 'pc_eingabe')
                with _eingabe_lock:
                    gui = _gui()
                    with pc.Z.lock:
                        pruefen(gui)
                    with pc.benutze('Eingabe', was):
                        for zeichen in (text if aktion == 'text' else [None]):
                            # Stop und Eingabe sind unter derselben Zustandssperre geordnet.
                            with pc.Z.lock:
                                pruefen(gui)
                                if aktion == 'text':
                                    _unicode(zeichen)
                                elif aktion == 'bewegen':
                                    gui.moveTo(x, y, duration=0)
                                elif aktion == 'klicken':
                                    gui.click(x=x, y=y, button=knopf)
                                elif aktion == 'scrollen':
                                    gui.scroll(schritte)
                                elif '+' in taste:
                                    _hotkey(gui, taste)
                                else:
                                    gui.press(taste)
                return 'Eingabe ausgefuehrt.'
            except Exception:
                pc._log(f'Eingabe abgebrochen: {was}')
                return 'Eingabe abgebrochen (Freigabe, Stop, Grenzen oder Eingabefehler).'

        # Das vorhandene Gate zeigt `an` per textContent/Telegram, loggt aber nur `was`.
        # Vorschau ausschliesslich fuer die menschliche Freigabe, niemals im Aktionslog.
        ziel = 'Hauptmonitor; physische Pixel; keine Passwoerter'
        if aktion == 'text':
            ziel += f' · Vorgeschlagener Text: «{text}»'
        return pc._mit_freigabe('pc_eingabe', was, genehmigt, an=ziel)
    except (ValueError, pc.Gesperrt):
        pc._log('Eingabe abgelehnt (ungueltig oder gesperrt).')
        return 'Eingabe abgelehnt (ungueltig oder gesperrt).'
