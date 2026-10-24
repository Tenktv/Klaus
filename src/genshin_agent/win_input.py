"""Normales Windows SendInput mit Scan-Codes; keine Treiber oder Spiel-Hooks."""
import ctypes as c
from ctypes import wintypes as w
import os

u = c.WinDLL('user32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
a = c.WinDLL('advapi32', use_last_error=True)

class Keyboard(c.Structure):
    _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                ('time', w.DWORD), ('extra', c.c_size_t)]

class Mouse(c.Structure):
    _fields_ = [('x', w.LONG), ('y', w.LONG), ('data', w.DWORD),
                ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]

class Payload(c.Union):
    _fields_ = [('keyboard', Keyboard), ('mouse', Mouse)]

class Input(c.Structure):
    _fields_ = [('type', w.DWORD), ('payload', Payload)]

u.SendInput.argtypes = [w.UINT, c.POINTER(Input), c.c_int]
u.SendInput.restype = w.UINT
u.MapVirtualKeyW.argtypes = [w.UINT, w.UINT]
u.MapVirtualKeyW.restype = w.UINT
k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k.OpenProcess.restype = w.HANDLE
k.CloseHandle.argtypes = [w.HANDLE]
a.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
a.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
a.GetSidSubAuthorityCount.argtypes = [c.c_void_p]
a.GetSidSubAuthorityCount.restype = c.POINTER(c.c_ubyte)
a.GetSidSubAuthority.argtypes = [c.c_void_p, w.DWORD]
a.GetSidSubAuthority.restype = c.POINTER(w.DWORD)
u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]


def integrity(pid):
    """Nur lesend: Windows-Integritätsstufe eines Prozesses, None bei unbekannt."""
    process = k.OpenProcess(0x1000, False, pid)
    if not process:
        return None
    token = w.HANDLE()
    try:
        if not a.OpenProcessToken(process, 8, c.byref(token)):
            return None
        size = w.DWORD()
        a.GetTokenInformation(token, 25, None, 0, c.byref(size))
        if not size.value:
            return None
        buffer = c.create_string_buffer(size.value)
        if not a.GetTokenInformation(token, 25, buffer, size, c.byref(size)):
            return None
        sid = c.cast(buffer, c.POINTER(c.c_void_p))[0]
        count = a.GetSidSubAuthorityCount(sid)[0]
        return a.GetSidSubAuthority(sid, count-1)[0]
    finally:
        if token:
            k.CloseHandle(token)
        k.CloseHandle(process)


def permission_status(handle):
    pid = w.DWORD()
    u.GetWindowThreadProcessId(handle, c.byref(pid))
    own, target = integrity(os.getpid()), integrity(pid.value)
    return {'agent_integrity': own, 'game_integrity': target,
            'blocked_by_uipi': own is not None and target is not None and own < target}


def ensure_permissions(handle):
    status = permission_status(handle)
    if status['blocked_by_uipi']:
        raise PermissionError('Windows-Rechtekonflikt: Genshin läuft mit höheren Rechten als der Agent. '
                              'Windows blockiert diese Eingaben (UIPI). Keine Aktion gesendet.')
    return status


def _send(event):
    events = (Input * 1)(event)
    c.set_last_error(0)
    count = u.SendInput(1, events, c.sizeof(Input))
    if count != 1:
        code = c.get_last_error()
        raise OSError(f'Windows nahm die Eingabe nicht an (SendInput={count}, Fehler={code}).')


def key(vk, up=False):
    scan = u.MapVirtualKeyW(vk, 0)
    if not scan:
        raise ValueError('Kein Scan-Code für diese Taste')
    event = Input(type=1)
    event.payload.keyboard = Keyboard(0, scan, 8 | (2 if up else 0), 0, 0)
    _send(event)


def mouse(flags, dx=0, dy=0, data=0):
    event = Input(type=0)
    event.payload.mouse = Mouse(dx, dy, data, flags, 0, 0)
    _send(event)
