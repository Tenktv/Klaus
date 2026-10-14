"""Gemeinsame Prozesssperre fuer Desktop-App und alten Voice-Starter."""
import atexit
import ctypes

_handle = None


def sperren():
    global _handle
    if _handle is not None:
        return True
    # Auch zwei unterschiedliche Checkouts duerfen nicht gleichzeitig den Lautsprecher bedienen.
    name = 'Local\\KlausAudioDesktopV1'
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise OSError('Klaus-Prozesssperre konnte nicht erstellt werden.')
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        return False
    _handle = handle
    atexit.register(kernel.CloseHandle, handle)
    return True
