import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import mss
from PIL import Image
from core import decide, InvalidDecision
import win_input

BASE = Path(__file__).resolve().parent
LOGS = BASE / 'logs'
STOP_FILE = BASE / 'stop.request'

user32 = ctypes.WinDLL('user32', use_last_error=True)
try:
    user32.SetProcessDPIAware()
except OSError:
    pass
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

VK = {'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44, 'f': 0x46,
      'space': 0x20, 'e': 0x45, 'q': 0x51, 'escape': 0x1B,
      **{str(n): 0x30+n for n in range(1, 5)}}


def foreground_identity():
    handle = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(handle, title, len(title))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    executable = ''
    if process:
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(path))
            if kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length)):
                executable = Path(path.value).name.lower()
        finally:
            kernel32.CloseHandle(process)
    return handle, title.value, executable


def window():
    handle, title, executable = foreground_identity()
    if executable not in ('genshinimpact.exe', 'yuanshen.exe'):
        return None
    rect = wintypes.RECT()
    point = wintypes.POINT(0, 0)
    if not user32.GetClientRect(handle, ctypes.byref(rect)) or not user32.ClientToScreen(handle, ctypes.byref(point)):
        return None
    if rect.right < 320 or rect.bottom < 240:
        return None
    return handle, {'left': point.x, 'top': point.y, 'width': rect.right, 'height': rect.bottom}


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Klaus – Genshin-Modus 0.2')
        self.root.geometry('800x680')
        self.stop = threading.Event()
        self.stop.set()
        self.running = False
        self.stop_reason = ''
        self.stop_stamp = STOP_FILE.stat().st_mtime_ns if STOP_FILE.exists() else 0
        self.messages = queue.Queue()
        self.key = tk.StringVar(value='')
        self.model = tk.StringVar(value='gemma3:4b')
        self.backend = tk.StringVar(value='local')
        self.goal = tk.StringVar(value='Verfolge die aktuell ausgewählte Storyquest bis zum nächsten abgeschlossenen Questabschnitt.')
        self.observe = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Bereit – Steuerung aktiv. Start drücken, dann ins Spiel wechseln.')
        panel = ttk.Frame(self.root, padding=15)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, textvariable=self.status, wraplength=750, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Label(panel, text='Lokale KI über Ollama – kein API-Schlüssel erforderlich.').pack(anchor='w', pady=(0, 10))
        for title, variable, secret in [('Lokales Bildmodell', self.model, False), ('Questziel', self.goal, False)]:
            ttk.Label(panel, text=title).pack(anchor='w')
            ttk.Entry(panel, textvariable=variable, show='*' if secret else '').pack(fill='x', pady=(0, 10))
        ttk.Checkbutton(panel, text='Beobachten: Entscheidungen anzeigen, keine Eingaben senden', variable=self.observe).pack(anchor='w')
        ttk.Label(panel, text='F8: Start (5 Sekunden zum Wechseln)   •   F9: Sofort stoppen\nNur der aktive Spielprozess erhält Eingaben. Maximal 10 Minuten / 100 Schritte.').pack(anchor='w', pady=10)
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Start / F8', command=self.start).pack(side='left')
        ttk.Button(buttons, text='STOP / F9', command=self.halt).pack(side='left', padx=8)
        ttk.Button(buttons, text='Bewegung testen (0,5 s W)', command=self.test_input).pack(side='left', padx=8)
        self.log = tk.Text(panel, height=13, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True, pady=10)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self.poll)

    def halt(self, reason='F9 oder STOP gedrückt'):
        if self.running and not self.stop.is_set():
            self.stop_reason = reason
            self.messages.put('Stopp: ' + reason)
        self.stop.set()

    def test_input(self):
        if self.running:
            self.messages.put('Zuerst den laufenden Agenten mit F9 stoppen.')
            return
        self.running = True
        self.stop_reason = ''
        self.stop.clear()
        threading.Thread(target=self.run_input_test, daemon=True).start()

    def run_input_test(self):
        try:
            self.messages.put('Bewegungstest: In 5 Sekunden wird W für 0,5 Sekunden gedrückt. Jetzt ins Spiel wechseln.')
            if self.stop.wait(5):
                return
            target = self.wait_for_game()
            if not target:
                self.messages.put('Test abgebrochen: aktives Genshin-Spielfenster nicht erkannt.')
                return
            status = win_input.ensure_permissions(target[0])
            self.messages.put('Windows-Rechteprüfung: ' + json.dumps(status))
            if self.execute({'type': 'key', 'key': 'w', 'seconds': 0.5}, target):
                self.messages.put('Windows hat W angenommen. Bewegung im Spiel bitte sichtbar prüfen; SendInput beweist keine Verarbeitung durch Genshin.')
        except Exception as error:
            self.messages.put(f'Testfehler: {type(error).__name__}: {error}')
        finally:
            self.stop.set()
            self.running = False

    def wait_for_game(self):
        deadline = time.monotonic() + 60
        last_message = 0
        while not self.stop.is_set() and time.monotonic() < deadline:
            target = window()
            if target:
                return target
            if time.monotonic() - last_message > 5:
                _, title, executable = foreground_identity()
                self.messages.put(f'Warte auf aktives Genshin-Fenster. Jetzt ins Spiel klicken. Aktiv: {title[:80]} ({executable or "Prozess nicht lesbar"}). F9 stoppt.')
                last_message = time.monotonic()
            self.stop.wait(0.2)
        return None

    def close(self):
        self.halt()
        self.root.destroy()

    def start(self):
        if self.running:
            return
        if self.backend.get() == 'openai' and not self.key.get().strip():
            self.messages.put('Bitte einen OpenAI API-Key eingeben. Ohne Key erfolgt keine KI-Steuerung.')
            return
        settings = (self.key.get().strip(), self.model.get().strip(), self.goal.get(), self.observe.get(), self.backend.get())
        self.stop.clear()
        self.stop_reason = ''
        self.running = True
        threading.Thread(target=self.run, args=settings, daemon=True).start()

    def poll(self):
        stamp = STOP_FILE.stat().st_mtime_ns if STOP_FILE.exists() else 0
        if stamp != self.stop_stamp:
            self.stop_stamp = stamp
            self.halt('Klaus hat den Spielmodus gestoppt')
        if user32.GetAsyncKeyState(0x78) & 0x8000:
            self.halt()
        pressed = bool(user32.GetAsyncKeyState(0x77) & 0x8000)
        if pressed and not getattr(self, 'f8_down', False):
            self.start()
        self.f8_down = pressed
        while not self.messages.empty():
            message = self.messages.get()
            self.status.set(message[:240])
            LOGS.mkdir(exist_ok=True)
            with (LOGS / 'runtime.log').open('a', encoding='utf-8') as output:
                output.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + message + '\n')
            self.log.configure(state='normal')
            self.log.insert('end', message + '\n')
            self.log.see('end')
            self.log.configure(state='disabled')
        self.root.after(50, self.poll)

    def execute(self, action, original):
        current = window()
        if self.stop.is_set():
            return False
        if not current or current != original:
            self.messages.put('Aktion verworfen: Spielfenster/Fokus hat sich seit dem Bild geändert. Neue Aufnahme erforderlich.')
            return False
        win_input.ensure_permissions(original[0])
        kind = action['type']
        if kind == 'key':
            key = VK[action['key']]
            win_input.key(key)
            try:
                end = time.monotonic() + action['seconds']
                while time.monotonic() < end:
                    if self.stop.wait(0.025) or window() != original:
                        self.halt('Stopp oder Fokusverlust während gehaltener Taste')
                        break
            finally:
                win_input.key(key, up=True)
        elif kind == 'click':
            rect = original[1]
            user32.SetCursorPos(rect['left'] + round(action['x']*(rect['width']-1)),
                                rect['top'] + round(action['y']*(rect['height']-1)))
            win_input.mouse(2)
            try:
                self.stop.wait(0.05)
            finally:
                win_input.mouse(4)
        elif kind == 'look':
            win_input.mouse(1, action['dx'], action['dy'])
        return True

    def run(self, key, model, goal, observe, backend):
        history = []
        invalid_count = 0
        deadline = time.monotonic() + 600
        ending = 'Schrittlimit erreicht'
        try:
            self.messages.put(('BEOBACHTEN – keine Eingaben. ' if observe else 'STEUERUNG AKTIV. ') + 'Start in 5 Sekunden. Jetzt zum Genshin-Fenster wechseln. F9 stoppt jederzeit.')
            if self.stop.wait(5):
                ending = self.stop_reason or 'Während Startverzögerung abgebrochen'
                return
            with mss.mss() as screen:
                for step in range(100):
                    if self.stop.is_set():
                        ending = self.stop_reason or 'Abgebrochen'
                        break
                    if time.monotonic() >= deadline:
                        ending = 'Zeitlimit von 10 Minuten erreicht'
                        break
                    target = self.wait_for_game()
                    if not target:
                        ending = self.stop_reason or '60 Sekunden kein aktives Genshin-Fenster erkannt'
                        break
                    if not observe:
                        win_input.ensure_permissions(target[0])
                    shot = screen.grab(target[1])
                    picture = Image.frombytes('RGB', shot.size, shot.rgb)
                    self.messages.put(f'Schritt {step+1}: Bild wird ausgewertet ({model}). Das kann lokal länger dauern. F9 stoppt.')
                    started = time.monotonic()
                    try:
                        decision = decide(picture, key, model, goal, history, backend)
                        invalid_count = 0
                    except InvalidDecision as error:
                        invalid_count += 1
                        self.messages.put(f'{error}. Keine Eingabe; erneute Aufnahme ({invalid_count}/3).')
                        if invalid_count >= 3:
                            ending = 'Drei ungültige Modellantworten hintereinander'
                            break
                        continue
                    if self.stop.is_set():
                        ending = self.stop_reason or 'Abgebrochen während Modellanfrage'
                        break
                    if time.monotonic() >= deadline:
                        ending = 'Zeitlimit während Modellanfrage erreicht; Aktion verworfen'
                        break
                    if not observe and time.monotonic() - started > 20:
                        ending = 'Bildentscheidung älter als 20 Sekunden; Aktion verworfen. Modell zunächst im Beobachtungsmodus aufwärmen.'
                        break
                    line = json.dumps(decision, ensure_ascii=False)
                    self.messages.put(f'{step+1}: {line}')
                    LOGS.mkdir(exist_ok=True)
                    with (LOGS / 'decisions.jsonl').open('a', encoding='utf-8') as output:
                        output.write(json.dumps({'time': time.time(), 'latency_s': round(time.monotonic()-started, 2), 'observe': observe, **decision}, ensure_ascii=False)+'\n')
                    history.append(decision)
                    if decision['action']['type'] == 'stop':
                        ending = 'Modell-Stopp: ' + decision['reason']
                        break
                    if not observe:
                        self.execute(decision['action'], target)
                    if self.stop.wait(1):
                        ending = self.stop_reason or 'Abgebrochen'
                        break
        except Exception as error:
            ending = f'{type(error).__name__}: {error}'
        finally:
            self.stop.set()
            self.running = False
            self.messages.put('Lauf beendet: ' + ending)


if __name__ == '__main__':
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel32.CreateMutexW(None, False, 'Local\\KlausGenshinAgent02')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if ctypes.get_last_error() != 183:
            App().root.mainloop()
    finally:
        kernel32.CloseHandle(mutex)
