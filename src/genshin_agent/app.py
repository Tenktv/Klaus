import ctypes
from ctypes import wintypes
import json
from pathlib import Path
from collections import deque
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.error

import mss
import numpy as np
from PIL import Image
from core import decide, dialog_lesen as ki_dialog, hint as ki_hinweis, InvalidDecision
import fertigkeiten
import reflexe
import kartenatlas
import kartensuche
import kartenspieler
import raetsel_db
import erkunden
import win_input

BASE = Path(__file__).resolve().parent
LOGS = BASE / 'logs'
DIAG = LOGS / 'diag'
BRUECKE = LOGS / 'bruecke'
# Wörter aus mitgelesenen Dialogen, die für Rätsel zählen (Element, Mechanik).
STICHWORTE = ('pyro', 'hydro', 'anemo', 'electro', 'cryo', 'geo', 'dendro', 'glide', 'wind current',
              'console', 'mechanism', 'chest', 'torch', 'monument', 'switch', 'pressure plate', 'climb')
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

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

VK = {'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44, 'f': 0x46, 'r': 0x52, 'x': 0x58, 'v': 0x56, 'm': 0x4D,
      'space': 0x20, 'shift': 0xA0, 'e': 0x45, 'q': 0x51, 'escape': 0x1B,
      **{str(n): 0x30+n for n in range(1, 6)}}


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



def tagesordner(basis):
    """Unterordner je Tag (logs/diag/2026-10-19): gleiche Uhrzeit am nächsten Tag überschreibt nichts."""
    ordner = basis / time.strftime('%Y-%m-%d')
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Klaus – Genshin-Modus 0.22')
        self.root.geometry('860x800')
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
        self.mode = tk.StringVar(value='autopilot')
        self.color = tk.StringVar(value='gold')
        self.sensitivity = tk.IntVar(value=1100)  # Startwert Mauszähler/Grad x100; wird nachgelernt
        self.team_text = tk.StringVar(value='1=anemo 2=pyro 3=hydro 4=cryo 5=pyro')
        self.bridge_start = tk.BooleanVar(value=False)
        self.allow_teleport = tk.BooleanVar(value=True)
        self.explore = tk.BooleanVar(value=False)
        self.bridge_active = False
        self.team = {}
        self.hint = None
        self.frame = None
        self.snapshot = False
        self.reset_dialog_state()
        self.status = tk.StringVar(value='Bereit – Steuerung aktiv. Start drücken, dann ins Spiel wechseln.')
        panel = ttk.Frame(self.root, padding=15)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, textvariable=self.status, wraplength=750, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Label(panel, text='Lokale KI über Ollama – kein API-Schlüssel erforderlich.').pack(anchor='w', pady=(0, 10))
        for title, variable, secret in [('Lokales Bildmodell', self.model, False), ('Questziel', self.goal, False)]:
            ttk.Label(panel, text=title).pack(anchor='w')
            ttk.Entry(panel, textvariable=variable, show='*' if secret else '').pack(fill='x', pady=(0, 10))
        modes = ttk.Frame(panel)
        modes.pack(fill='x', pady=(0, 6))
        ttk.Radiobutton(modes, text='Autopilot: Reflexe + KI gleichzeitig (empfohlen)', value='autopilot', variable=self.mode).pack(side='left')
        ttk.Radiobutton(modes, text='Nur KI-Schritte (langsam)', value='ki', variable=self.mode).pack(side='left', padx=12)
        tuning = ttk.Frame(panel)
        tuning.pack(fill='x', pady=(0, 6))
        ttk.Label(tuning, text='Questfarbe').pack(side='left')
        ttk.Combobox(tuning, textvariable=self.color, values=sorted(reflexe.FARBEN), width=6, state='readonly').pack(side='left', padx=(4, 16))
        ttk.Label(tuning, text='Kamera-Empfindlichkeit').pack(side='left')
        ttk.Spinbox(tuning, textvariable=self.sensitivity, from_=100, to=3000, increment=100, width=6).pack(side='left', padx=4)
        ttk.Label(tuning, text='Team (Slot=Element)').pack(side='left', padx=(16, 4))
        ttk.Entry(tuning, textvariable=self.team_text, width=34).pack(side='left')
        ttk.Checkbutton(panel, text='Beobachten: Entscheidungen anzeigen, keine Eingaben senden', variable=self.observe).pack(anchor='w')
        ttk.Checkbutton(panel, text='Direkt mit Claude-Steuerung starten (Rätsel; Claude schickt Befehle über logs/bruecke)',
                        variable=self.bridge_start).pack(anchor='w')
        ttk.Checkbutton(panel, text='Teleportieren, wenn das Questziel weit weg ist (Karte → Questsymbol → nächster Teleportpunkt)',
                        variable=self.allow_teleport).pack(anchor='w')
        ttk.Checkbutton(panel, text='Erkunden statt Quest: Truhen, Okuli, Teleportpunkte, Statuen, Domänen der Umgebung (Position per Karte)',
                        variable=self.explore).pack(anchor='w')
        ttk.Label(panel, text='F8: Start   •   F9: Sofort stoppen   •   F10: Spielbild speichern   •   F11: Claude-Steuerung an/aus\n'
                              'Autopilot: läuft bis 60 Minuten, pausiert automatisch, wenn das Spiel nicht im Vordergrund ist.').pack(anchor='w', pady=10)
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Start / F8', command=self.start).pack(side='left')
        ttk.Button(buttons, text='STOP / F9', command=self.halt).pack(side='left', padx=8)
        ttk.Button(buttons, text='Bewegung testen (0,5 s W)', command=self.test_input).pack(side='left', padx=8)
        ttk.Button(buttons, text='Als Admin neu starten', command=self.restart_elevated).pack(side='left', padx=8)
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
        self.stop.clear()
        self.stop_reason = ''
        self.running = True
        if self.mode.get() == 'autopilot':
            try:
                sensitivity = max(100, min(3000, int(self.sensitivity.get())))
            except (tk.TclError, ValueError):
                sensitivity = 1100
            self.team = fertigkeiten.team_lesen(self.team_text.get())
            self.bridge_active = self.bridge_start.get()
            self.teleport_ok = self.allow_teleport.get()
            self.explore_ok = self.explore.get()
            settings = (self.model.get().strip(), self.goal.get(), self.observe.get(), self.color.get(), sensitivity)
            threading.Thread(target=self.autopilot, args=settings, daemon=True).start()
            return
        settings = (self.key.get().strip(), self.model.get().strip(), self.goal.get(), self.observe.get(), self.backend.get())
        threading.Thread(target=self.run, args=settings, daemon=True).start()

    def restart_elevated(self):
        """Startet dieses Panel mit Admin-Rechten neu; Windows fragt per UAC nach."""
        if self.running:
            self.messages.put('Zuerst mit F9 stoppen.')
            return
        python = Path(sys.executable)
        if python.with_name('pythonw.exe').exists():
            python = python.with_name('pythonw.exe')
        shell32 = ctypes.WinDLL('shell32')
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        result = shell32.ShellExecuteW(None, 'runas', str(python), f'"{Path(__file__).resolve()}"', str(BASE), 1)
        if (result or 0) <= 32:
            self.messages.put('Admin-Start abgebrochen oder abgelehnt. Ohne Admin-Rechte blockiert Windows die Eingaben in Genshin.')
            return
        self.root.after(200, self.close)

    def poll(self):
        stamp = STOP_FILE.stat().st_mtime_ns if STOP_FILE.exists() else 0
        if stamp != self.stop_stamp:
            self.stop_stamp = stamp
            self.halt('Klaus hat den Spielmodus gestoppt')
        if user32.GetAsyncKeyState(0x78) & 0x8000:
            self.halt()
        if user32.GetAsyncKeyState(0x79) & 0x8000 and self.running:
            self.snapshot = True  # F10: nächstes Spielbild in voller Größe speichern
        f11 = bool(user32.GetAsyncKeyState(0x7A) & 0x8000)
        if f11 and not getattr(self, 'f11_down', False) and self.running and self.mode.get() == 'autopilot':
            self.bridge_active = not self.bridge_active
            self.messages.put('CLAUDE-STEUERUNG AN – Autopilot pausiert, Claude schickt die Befehle.' if self.bridge_active
                              else 'Claude-Steuerung aus – Autopilot übernimmt wieder.')
        self.f11_down = f11
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

    def command(self, order, target):
        """Einen Reflex-Befehl ausführen, nur solange das Spiel im Vordergrund ist."""
        kind = order[0]
        if kind == 'loslassen':
            win_input.key(VK[order[1]], up=True)  # Loslassen ist immer harmlos
            return True
        if self.stop.is_set() or window() != target:
            return False
        if kind == 'halten':
            win_input.key(VK[order[1]])
        elif kind == 'tippen':
            win_input.key(VK[order[1]])
            try:
                self.stop.wait(order[2] if len(order) > 2 else 0.07)
            finally:
                win_input.key(VK[order[1]], up=True)
        elif kind == 'ausweichen':
            seite, dauer = order[1:]
            if seite not in ('a', 'd') or not .05 <= dauer <= .2:
                raise ValueError('Ausweichen erlaubt nur kurze seitliche Sprints.')
            try:
                win_input.key(VK[seite])
                win_input.key(VK['shift'])
                if self.stop.wait(dauer) or window() != target:
                    return False
            finally:
                win_input.key(VK['shift'], up=True)
                win_input.key(VK[seite], up=True)
        elif kind == 'blick':
            win_input.mouse(1, int(order[1]), int(order[2]))
        elif kind == 'klick':
            win_input.mouse(2)
            try:
                self.stop.wait(0.04)
            finally:
                win_input.mouse(4)
        elif kind == 'maus_halten':
            win_input.mouse(2)
            try:
                self.stop.wait(order[1])
            finally:
                win_input.mouse(4)
        elif kind == 'maus_klick':
            # Nur in Menüs/Karte (dort ist der Mauszeiger sichtbar): an Bildposition x/y (0..1) klicken.
            rect = target[1]
            user32.SetCursorPos(rect['left'] + round(order[1] * (rect['width'] - 1)),
                                rect['top'] + round(order[2] * (rect['height'] - 1)))
            self.stop.wait(0.08)
            win_input.mouse(2)
            try:
                self.stop.wait(0.06)
            finally:
                win_input.mouse(4)
        elif kind in ('karte_zoom', 'karte_ziehen'):
            # Interne Kartenbefehle. Die Suche bestätigt vor jedem Befehl die
            # Weltkarte; Fokus und Stopp gelten auch während eines Ziehens.
            rect = target[1]

            def position(x, y):
                return user32.SetCursorPos(rect['left'] + round(x * (rect['width'] - 1)),
                                           rect['top'] + round(y * (rect['height'] - 1)))

            if kind == 'karte_zoom':
                # Eine Rastung ändert den Maßstab nur um ~2 % (Zoomregler 23:00 kaum bewegt) –
                # ein Suchschritt sendet deshalb mehrere Rastungen, höchstens 15.
                rasten = order[1]
                if not isinstance(rasten, int) or not 1 <= abs(rasten) <= 15:
                    raise ValueError('Kartenzoom erlaubt 1 bis 15 Rastungen je Bild.')
                if not position(.52, .55) or not self.command(('warten', .08), target):
                    return False
                for _ in range(abs(rasten)):
                    win_input.mouse(0x0800, data=120 if rasten > 0 else -120)
                    if not self.command(('warten', .03), target):
                        return False
            else:
                x0, y0, x1, y1 = order[1:]
                if not all(.2 <= x <= .82 for x in (x0, x1)) or not all(.12 <= y <= .85 for y in (y0, y1)):
                    raise ValueError('Kartenziehen muss innerhalb der freien Kartenfläche bleiben.')
                if not position(x0, y0) or not self.command(('warten', .08), target):
                    return False
                win_input.mouse(2)
                try:
                    for i in range(1, 13):
                        if not self.command(('warten', .025), target):
                            return False
                        if not position(x0 + (x1-x0)*i/12, y0 + (y1-y0)*i/12):
                            return False
                finally:
                    win_input.mouse(4)
        elif kind == 'warten':
            end = time.monotonic() + order[1]
            while time.monotonic() < end:
                if self.stop.wait(min(0.1, max(0.0, end - time.monotonic()))) or window() != target:
                    return False
        return True

    def teleport(self, look, target):
        """Questziel weit weg: Karte (M) → goldenes Questsymbol suchen → den freigeschalteten
        Teleportpunkt anklicken, der dem Symbol am nächsten liegt → F („Teleport“). Jeder Schritt
        wird am Bild geprüft; bei Unsicherheit Menüs mit ESC schließen und normal weiterlaufen.
        („Navigate“ im Questbuch öffnet die Karte nicht, es startet nur die Navigation.)"""
        def step(order, pause):
            return self.command(order, target) and self.command(('warten', pause), target)

        self.teleport_fehler = None
        self.messages.put('Teleport: Questziel weit weg – öffne die Karte (M).')
        if not step(('tippen', 'm', 0.08), 1.0):
            return False
        picture = look()
        map_open = False
        # Die Karte blendet ein. Ruckelt das Spiel, kommt sie erst nach Sekunden (Livelauf 22:55:
        # nach ~8 s, während das KI-Modell lud) – bis zu 20 frische Bilder im Abstand von 0,5 s.
        for attempt in range(20):
            map_open = reflexe.karte_offen(picture)
            if map_open:
                break
            if attempt < 19:
                if not self.command(('warten', 0.5), target):
                    return False
                picture = look()
        if not map_open:
            self.save_diag(picture, {'modus': 'Teleport: Karte ging nicht auf'})
            self.teleport_fehler = 'karte_zu'
            self.messages.put('Teleport abgebrochen: Karte ging nicht auf (Bild in logs/diag) – neuer Versuch in 20 s.')
            return self.close_menus(look, target)
        self.position_merken(picture, 'Karte')
        picture, quest, candidates = kartensuche.suchen(
            picture, look, lambda order: self.command(order, target), self.messages.put,
            diagnose=lambda bild, info: self.save_diag(bild, {'modus': 'Kartensuche', **info}))
        if quest is None:
            self.save_diag(picture, {'modus': 'Teleport: Questsymbol fehlt', 'karte_offen': True})
            self.messages.put('Teleport abgebrochen: kein Questziel im geprüften Kartenbereich gefunden oder Suche unterbrochen.')
            return self.close_menus(look, target)
        if not candidates:
            self.save_diag(picture, {'modus': 'Teleport: kein freies Ziel', 'quest': quest,
                                     'ziele': reflexe.teleportziele(picture)})
            self.messages.put('Teleport abgebrochen: kein freigeschalteter Wegpunkt oder Statue im geprüften Zielbereich.')
            return self.close_menus(look, target)
        for attempt in range(3):
            if not candidates:
                break
            point = candidates[0]
            self.messages.put('Teleport: wähle ' + ('Statue der Sieben' if point.get('art') == 'statue' else 'Wegpunkt')
                              + f' bei x={point["x"]:.3f}, y={point["y"]:.3f}.'
                              + (f' Verkürzt die Kartenstrecke um ca. {point["weg_ersparnis"]:.0%}.'
                                 if 'weg_ersparnis' in point else ''))
            before = reflexe.teleportpunkte(picture)
            ziel_bild = picture
            if not step(('maus_klick', point['x'], point['y']), 1.0):
                return False
            picture = look()
            if not reflexe.teleport_knopf(picture):
                # Liegen Symbole übereinander, erscheint eine Auswahlliste; ihr Eintrag
                # „Teleport Waypoint“ trägt ein Pin-Symbol, das vorher nicht da war.
                new = [q for q in reflexe.teleportpunkte(picture)
                       if all(abs(q['x'] - b['x']) + abs(q['y'] - b['y']) > 0.02 for b in before)]
                if new:
                    if not step(('maus_klick', new[0]['x'], new[0]['y']), 1.0):
                        return False
                    picture = look()
            if reflexe.teleport_knopf(picture):
                self.messages.put('Teleport: Teleportpunkt gewählt – los (F).')
                if step(('tippen', 'f', 0.08), 1.0):
                    self.position_merken(ziel_bild, 'Teleportziel', (point['x'], point['y']))
                    return True
                return False
            # Kein Teleport-Knopf (gesperrt o. Ä.): Fenster schließen, nächsten Punkt versuchen.
            if not step(('tippen', 'escape', 0.08), 0.8):
                return False
            picture = look()
            if not reflexe.karte_offen(picture):
                break
            # Kartenausschnitt kann sich beim Öffnen/Schließen einer Auswahl
            # verschoben haben. Nur frisch vermessene Ziele erneut versuchen.
            quest = reflexe.raute(picture, weltkarte=True)
            candidates = kartensuche.kandidaten(picture, quest)
        self.save_diag(picture, {'modus': 'Teleport: Bestätigung fehlt', 'quest': quest})
        self.messages.put('Teleport abgebrochen: bei der Punktauswahl erschien kein Teleport-Knopf.')
        return self.close_menus(look, target)

    def position_merken(self, picture, quelle, punkt=None, vorwissen=None):
        """Atlasposition für Rätsel-Hinweise merken: Spielerpfeil auf der offenen Karte oder das
        gewählte Teleportziel. Ohne sichere Kartenzuordnung bleibt die alte Position. vorwissen =
        (x, y, y_sign) geschätzter Standort: Dann genügt mit dem zuletzt gemessenen Maßstab ein Symbol."""
        try:
            transform = kartenatlas.lokalisieren(picture)
            pfeil = kartenspieler.spieler(picture) if punkt is None else None
            massstab = getattr(self, 'letzter_massstab', None)
            if transform is None and vorwissen is not None and pfeil is not None and massstab:
                transform = kartenatlas.lokalisieren_nahe(picture, pfeil[:2], vorwissen[:2], massstab, vorwissen[2])
            if transform is None:
                return
            if not transform.get('vorwissen'):
                self.letzter_massstab = transform['scale']
            if punkt is None:
                if pfeil is None:
                    return
                punkt = pfeil[:2]
            hoehe, breite = picture.shape[:2]
            x, y = raetsel_db.atlas_position(transform, punkt[0], punkt[1], breite, hoehe)
            self.atlas_position = (x, y, time.monotonic(), quelle)
            stand = (x, y, transform['y_sign'])
            # Wegpunkte/Statuen im Bild (blau = frei, grau = gesperrt) für den Erkundungsmodus.
            self.kartensymbole = [(*raetsel_db.atlas_position(transform, z['x'], z['y'], breite, hoehe), z['offen'], z['art'])
                                  for z in reflexe.teleportziele(picture) if z.get('sicher', True)]
            naehe = raetsel_db.in_der_naehe(x, y)
            if naehe:
                self.messages.put(f'Rätsel/Truhen in der Nähe ({quelle}): '
                                  + '; '.join(f"{p['typ']} {p['abstand']}" for p in naehe[:4]))
            return stand
        except (OSError, ValueError, KeyError):
            return None

    def position_bestimmen(self, look, target, vorwissen=None):
        """Erkundung: Karte kurz öffnen, Standort aus Atlas-Abgleich + Spielerpfeil lesen, Karte
        schließen. (x, y, y_sign) in Atlas-Metern oder None. Ohne genug Symbole (dünn besiedelte
        Gegend) bis zu dreimal herauszoomen, danach wieder auf den alten Zoom – der Maßstab für die
        Bestimmung mit Vorwissen bleibt so gültig."""
        if not self.command(('tippen', 'm', 0.08), target):
            return None
        picture = None
        for _ in range(20):
            if not self.command(('warten', 0.5), target):
                return None
            picture = look()
            if reflexe.karte_offen(picture):
                break
        else:
            self.messages.put('Erkunden: Karte ging nicht auf.')
            self.close_menus(look, target)
            return None
        stand = self.position_merken(picture, 'Erkundung', vorwissen=vorwissen)
        rausgezoomt = 0
        while stand is None and rausgezoomt < 3:
            if not (self.command(('karte_zoom', -kartensuche.ZOOM_RASTEN), target)
                    and self.command(('warten', 1.0), target)):
                break
            rausgezoomt += 1
            picture = look()
            stand = self.position_merken(picture, 'Erkundung')
        for _ in range(rausgezoomt):
            if not self.command(('karte_zoom', kartensuche.ZOOM_RASTEN), target):
                break
        if stand is None:
            self.save_diag(picture, {'modus': 'Erkunden: Position nicht bestimmbar'})
            self.messages.put('Erkunden: Position auf der Karte nicht bestimmbar (Bild in logs/diag).')
        self.close_menus(look, target)
        return stand

    def close_menus(self, look, target):
        """ESC, bis das normale Spielbild wieder da ist (höchstens dreimal)."""
        for attempt in range(3):
            picture = look()
            if reflexe.hud_sichtbar(picture, picture):
                break
            if not (self.command(('tippen', 'escape', 0.08), target) and self.command(('warten', 1.0), target)):
                break
        return False

    def bridge_write(self, full, info, pilot, state, game_active=True):
        """Zustand + Spielbild (nur Genshin-Fenster) für Claude ablegen; atomar ersetzen.
        Liest Claude die Datei gerade (Windows sperrt dann das Ersetzen), wird es im nächsten
        Durchlauf erneut versucht, statt die Schleife abzubrechen."""
        BRUECKE.mkdir(parents=True, exist_ok=True)
        after = state['nr'] if full is not None else state['bild_nach_nr']
        data = {'nr': state['nr'], 'bild_nach_nr': after, 'zeit': time.time(),
                'spiel_aktiv': game_active, 'ergebnis': state['ergebnis'],
                'erkennung': {k: info.get(k) for k in ('hud', 'ziel', 'raute', 'kegel', 'dialog', 'laden', 'gegner', 'bewegt')} if info else None,
                'lenkung_zaehler_pro_grad': round(pilot.zaehler_pro_grad, 2), 'team': self.team}
        position = getattr(self, 'atlas_position', None)
        if position is not None:
            # Hinweise der HoYoLAB-Community zu Rätseln/Truhen um die zuletzt bekannte Position.
            data['position'] = {'atlas': [round(position[0]), round(position[1])], 'quelle': position[3],
                                'alter_s': round(time.monotonic() - position[2])}
            data['raetsel_in_der_naehe'] = raetsel_db.kurz(raetsel_db.in_der_naehe(position[0], position[1]))
        try:
            if full is not None:
                picture = Image.fromarray(full)
                picture.thumbnail((1280, 720))
                picture.save(BRUECKE / 'bild.tmp.jpg', format='JPEG', quality=85)
                self._replace(BRUECKE / 'bild.tmp.jpg', BRUECKE / 'bild.jpg')
            (BRUECKE / 'zustand.tmp.json').write_text(json.dumps(data, ensure_ascii=False, default=str), encoding='utf-8')
            self._replace(BRUECKE / 'zustand.tmp.json', BRUECKE / 'zustand.json')
        except OSError:
            return False
        state['bild_nach_nr'] = after
        state['geschrieben'] = time.monotonic()
        return True

    def _replace(self, source, target, attempts=5):
        for attempt in range(attempts):
            try:
                source.replace(target)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.02)

    def bridge_take(self, state):
        """Neue Befehlsdateien von Claude einsammeln (älteste zuerst), verarbeitete löschen."""
        found = []
        for path in BRUECKE.glob('befehl_*.json'):
            try:
                nr = int(path.stem.split('_', 1)[1])
                age = time.time() - path.stat().st_mtime
                data = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError) as error:
                state['ergebnis'] = {'ok': False, 'fehler': f'Befehlsdatei unlesbar: {error}'}
                path.unlink(missing_ok=True)
                continue
            path.unlink(missing_ok=True)
            if age > 30:
                state['ergebnis'] = {'ok': False, 'fehler': f'Befehl {nr} war {age:.0f} s alt – verworfen'}
            elif nr > state['nr']:
                found.append((nr, data))
        return sorted(found, key=lambda item: item[0])

    def bridge_execute(self, data, target, pilot):
        try:
            plan = fertigkeiten.pruefen(data.get('befehle') if isinstance(data, dict) else None,
                                        pilot.zaehler_pro_grad, self.team)
        except fertigkeiten.Ungueltig as error:
            return {'ok': False, 'fehler': str(error), 'ausgefuehrt': 0}
        held = set()
        try:
            for done, orders in enumerate(plan):
                for order in orders:
                    if order[0] == 'halten':
                        held.add(order[1])
                    elif order[0] == 'loslassen':
                        held.discard(order[1])
                    if not self.command(order, target):
                        return {'ok': False, 'fehler': 'Abgebrochen: Spiel nicht mehr im Vordergrund oder F9',
                                'ausgefuehrt': done}
            return {'ok': True, 'ausgefuehrt': len(plan)}
        finally:
            for key in held:
                self.command(('loslassen', key), target)

    def bridge_step(self, full, info, target, pilot, state):
        """Ein Durchlauf im Claude-Modus: Befehle ausführen, danach frisches Bild ablegen."""
        BRUECKE.mkdir(parents=True, exist_ok=True)
        for nr, data in self.bridge_take(state):
            state['nr'] = nr
            state['ergebnis'] = self.bridge_execute(data, target, pilot)
            self.messages.put(f'Claude-Befehl {nr}: {json.dumps(data, ensure_ascii=False)[:150]} → '
                              f'{"ok" if state["ergebnis"]["ok"] else state["ergebnis"]["fehler"]}')
            state['frisch_ab'] = time.monotonic() + 0.35  # Bild erst nach der Wirkung aufnehmen
            return
        now = time.monotonic()
        waiting = state['bild_nach_nr'] < state['nr']
        if now >= state['frisch_ab'] and (waiting or now - state['geschrieben'] > 2.0):
            self.bridge_write(full, info, pilot, state)

    def reset_dialog_state(self):
        self.in_dialog = False
        self.dialog_jobs = deque(maxlen=8)  # Zeilen (Ausschnitte), die Gemma noch vorlesen soll
        self.last_line = None
        self.keywords = deque(maxlen=40)  # (zeit, wort) aus mitgelesenen Dialogen

    def track_dialog(self, info, picture, full, state, now, reading):
        """Neue Dialogzeile erkennen und – sobald der Text steht – zum Vorlesen vormerken.
        Der Pilot klickt trotzdem im Takt weiter: Gemma braucht bei laufendem Spiel 10-20 s pro
        Zeile; wartete er darauf, blieb der Dialog stehen. Vorgelesen wird nebenher."""
        self.in_dialog = info['dialog']
        info['dialog_bereit'] = True
        if not info['dialog'] or not reading:
            state['sig'] = None
            return
        # Fingerabdruck nur aus der weißen Schrift: bewegter Hintergrund ändert ihn nicht.
        sig = reflexe.dialog_signatur(picture)
        # Echte neue Zeilen unterscheiden sich um 0,04-0,07, bewegter Hintergrund um 0,0.
        if state['sig'] is None or float(np.abs(sig - state['sig']).mean()) > 0.02:
            state.update(sig=sig, since=now, stable=0)
            return
        state['stable'] += 1
        if state['stable'] == 3 and (state.get('queued') is None or float(np.abs(sig - state['queued']).mean()) > 0.02):
            state['queued'] = sig
            self.dialog_jobs.append(reflexe.dialog_ausschnitt(full))

    def record_line(self, line):
        text = ' '.join(line['text'].split())
        if not text or text == self.last_line:
            return
        self.last_line = text
        speaker = line['sprecher'] or '–'
        self.messages.put(f'💬 {speaker}: {text}')
        LOGS.mkdir(exist_ok=True)
        with (LOGS / 'dialoge.txt').open('a', encoding='utf-8') as output:
            output.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")}  {speaker}: {text}\n')
        lower = text.lower()
        for word in STICHWORTE:
            if word in lower:
                self.keywords.append((time.monotonic(), word))

    def brain(self, model, goal):
        """Gemma läuft parallel: liest Dialogzeilen (Vorrang) und zeigt sonst, wohin es weitergeht.
        Der Körper wartet nie auf Gemma – nur im Dialog bis die Zeile gelesen ist (max. 6 s)."""
        pointers = []
        while not self.stop.is_set():
            if self.dialog_jobs:
                crop = self.dialog_jobs.popleft()
                try:
                    self.record_line(ki_dialog(Image.fromarray(crop), model))
                except (InvalidDecision, urllib.error.URLError, TimeoutError, ConnectionError) as error:
                    self.messages.put(f'Dialog nicht lesbar ({error}).')
                continue
            frame = self.frame
            # Im Claude-Modus, während Dialogen und mit altem Bild (Spiel nicht im Vordergrund)
            # keine Zeigehinweise – Grafikkarte freihalten.
            if frame is None or self.bridge_active or self.in_dialog or time.monotonic() - frame[2] > 3:
                self.stop.wait(0.2)
                continue
            picture, camera, captured = frame
            started = time.monotonic()
            try:
                result = ki_hinweis(Image.fromarray(picture), model, goal)
            except InvalidDecision as error:
                self.messages.put(f'KI: {error} – nächstes Bild.')
                continue
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                self.messages.put(f'KI nicht erreichbar ({error}). Reflexe laufen ohne KI weiter; neuer Versuch in 15 s.')
                self.stop.wait(15)
                continue
            if self.stop.is_set():
                break
            # Gemma 4B nennt oft stur denselben Wert (meist 0.20), egal was zu sehen ist:
            # zeigt sie viermal fast gleich, gilt das Zeigen als wertlos.
            pointers = (pointers + [result['goal_x']])[-4:]
            stuck = len(pointers) == 4 and None not in pointers and max(pointers) - min(pointers) < 0.06
            # Bildposition + Kamerarichtung beim Aufnehmen = feste Himmelsrichtung zum Ziel.
            if result['goal_x'] is not None and camera is not None and not stuck:
                result['ziel_kurs'] = (camera + reflexe.bildwinkel(result['goal_x'])) % 360
            result['erfasst'] = captured
            self.hint = result
            latency = round(time.monotonic() - started, 1)
            pointer = f'Ziel x={result["goal_x"]:.2f}' if result['goal_x'] is not None else 'kein Ziel'
            if stuck:
                pointer += ' (ignoriert, zeigt immer gleich)'
            self.messages.put(f'KI ({latency} s): {result["scene"]}, {pointer} – {result["state"][:110]}')
            LOGS.mkdir(exist_ok=True)
            with (LOGS / 'decisions.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps({'time': time.time(), 'latency_s': latency, 'autopilot': True, **result}, ensure_ascii=False) + '\n')

    def record_combat(self, picture, info, mode, orders, seconds):
        """Kampfrekorder: pro Sekunde ein Bild (540p, nur Genshin) plus eine Zeile in
        logs/kampf.jsonl – Modus, Gegner, Pfeile, HP und die gesendeten Befehle. So lässt sich
        später genau nachvollziehen, was im Kampf erkannt und getan wurde. Nichts wird gelöscht
        (Nikola: „die sollen bleiben“); ein Ordner je Tag."""
        try:
            ordner = tagesordner(LOGS / 'kampf')
            name = f'{time.strftime("%H%M%S")}.jpg'
            Image.fromarray(picture).save(ordner / name, quality=80)
            row = {'datum': ordner.name, 'zeit': time.strftime('%H:%M:%S'), 'bild': f'{ordner.name}/{name}',
                   'modus': mode, 'sek_im_kampf': round(seconds, 1),
                   'gegner': info.get('gegner'), 'pfeile': info.get('pfeile'), 'hp': info.get('eigene_hp'),
                   'herausforderung': info.get('herausforderung'), 'kampfziel': info.get('kampfziel'),
                   'q_bereit': info.get('q_bereit'), 'team_aktiv': info.get('team_aktiv'),
                   'team_q': info.get('team_q'), 'bewegt': info.get('bewegt'),
                   'befehle': [list(o) for o in orders]}
            with (LOGS / 'kampf.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
        except OSError:
            pass

    def save_diag(self, picture, info, full=None):
        """Nur Spielbild (kein Desktop) zur Kalibrierung, in logs/diag/<Datum>/. Nichts wird gelöscht:
        Früher blieben nur 40 Bilder, und weil die Namen nur Uhrzeiten waren, löschte er heutige
        22:xx-Bilder statt der von gestern 23:xx (Nikola: „die sollen bleiben“)."""
        ordner = tagesordner(DIAG)
        stamp = time.strftime('%H%M%S')
        Image.fromarray(picture).save(ordner / f'{stamp}.jpg', quality=80)
        if full is not None:
            Image.fromarray(np.ascontiguousarray(reflexe.karte_ausschneiden(full)[0])).save(ordner / f'{stamp}_karte.png')
        (ordner / f'{stamp}.json').write_text(json.dumps(info, default=str), encoding='utf-8')

    def save_trace(self, frames, modus):
        """Kurze Bildfolge vor Fall/Ausweichmanöver, höchstens sechs pro Lauf."""
        try:
            ziel = DIAG / 'verlauf' / (time.strftime('%Y%m%d_%H%M%S') + f'_{time.time_ns()%1000000:06d}')
            ziel.mkdir(parents=True, exist_ok=False)
            daten = []
            for i, (picture, info) in enumerate(frames):
                name = f'{i:02d}.jpg'
                Image.fromarray(picture).save(ziel / name, quality=85)
                daten.append({'bild': name, **info})
            (ziel / 'zustand.json').write_text(json.dumps({'modus': modus, 'bilder': daten}, default=str),
                                               encoding='utf-8')
        except OSError as error:
            self.messages.put(f'Diagnosefolge konnte nicht gespeichert werden: {error}')

    def autopilot(self, model, goal, observe, color, sensitivity):
        pilot = reflexe.Pilot(sensitivity, team=self.team, teleport=getattr(self, 'teleport_ok', False))
        if getattr(self, 'explore_ok', False):
            pilot.erkunder = erkunden.Erkunder()
            self.messages.put(f'Erkunden: {len(pilot.erkunder.erledigt)} Ziele schon erledigt – Truhen, Okuli, '
                              'gesperrte Teleportpunkte/Statuen und Domänen im Umkreis von 400 m, Position per Karte.')
        analyse = reflexe.Analyse(color)
        dialog_state = {'sig': None, 'since': 0.0, 'stable': 0}
        self.reset_dialog_state()
        target = None
        self.snapshot = False
        bridge = {'nr': 0, 'bild_nach_nr': 0, 'ergebnis': None, 'frisch_ab': 0.0, 'geschrieben': 0.0}
        bridge_was = False
        verlauf = deque(maxlen=6)
        belege = 0
        letzter_beleg = -1e9
        vorher_luft = False
        vorher_hp = None
        try:
            # Laufende Nummer fortsetzen, damit alte Befehlsdateien nie erneut ausgeführt werden.
            bridge['nr'] = bridge['bild_nach_nr'] = json.loads((BRUECKE / 'zustand.json').read_text(encoding='utf-8'))['nr']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        for stale in BRUECKE.glob('befehl_*.json') if BRUECKE.exists() else []:
            stale.unlink(missing_ok=True)
        ending = 'Zeitlimit von 60 Minuten erreicht'
        self.hint, self.frame = None, None
        try:
            self.messages.put(('BEOBACHTEN – keine Eingaben. ' if observe else 'AUTOPILOT AKTIV. ')
                              + 'Start in 5 Sekunden. Jetzt ins Spiel wechseln. F9 stoppt jederzeit.')
            if self.stop.wait(5):
                ending = self.stop_reason or 'Während Startverzögerung abgebrochen'
                return
            if model:
                threading.Thread(target=self.brain, args=(model, goal), daemon=True).start()
            deadline = time.monotonic() + 3600
            last_mode, last_report, last_diag, away_since = '', 0.0, 0.0, None
            letzter_kampf, kampf_start = 0.0, time.monotonic()
            checked = None
            with mss.mss() as screen:
                while not self.stop.is_set():
                    now = time.monotonic()
                    if now >= deadline:
                        break
                    current = window()
                    if not current:
                        for order in pilot.alles_loslassen():
                            self.command(order, None)
                        if away_since is None:
                            away_since = now
                            self.messages.put('Pausiert: Genshin ist nicht im Vordergrund. Zurück ins Spiel klicken, dann geht es weiter.')
                        if self.bridge_active:
                            # Befehle nie verspätet ausführen: ablehnen, solange das Spiel nicht vorn ist.
                            BRUECKE.mkdir(parents=True, exist_ok=True)
                            for nr, _ in self.bridge_take(bridge):
                                bridge['nr'] = bridge['bild_nach_nr'] = nr
                                bridge['ergebnis'] = {'ok': False, 'fehler': 'Spiel nicht im Vordergrund – nichts ausgeführt'}
                            if now - bridge['geschrieben'] > 2.0:
                                self.bridge_write(None, None, pilot, bridge, game_active=False)
                        if now - away_since > 600:
                            ending = '10 Minuten ohne aktives Spielfenster'
                            break
                        self.stop.wait(0.3)
                        continue
                    if away_since is not None:
                        self.messages.put('Weiter: Spielfenster wieder aktiv.')
                        away_since = None
                    target = current
                    if not observe and checked != target[0]:
                        win_input.ensure_permissions(target[0])
                        checked = target[0]
                    shot = screen.grab(target[1])
                    full = np.frombuffer(shot.rgb, np.uint8).reshape(shot.height, shot.width, 3)
                    picture = reflexe.verkleinern(full)
                    info = analyse(picture, full)
                    verlauf.append((picture.copy(), {k: info.get(k) for k in
                        ('faellt', 'gleitet', 'gleiter_zu', 'fall_messung', 'eigene_hp',
                         'gegner', 'gegner_frisch', 'pfeile', 'kampfziel', 'q_bereit', 'ziel', 'spur', 'klettert')}))
                    if self.bridge_active != bridge_was:
                        bridge_was = self.bridge_active
                        for order in pilot.alles_loslassen():
                            self.command(order, target)
                    if self.bridge_active and not observe:
                        self.bridge_step(full, info, target, pilot, bridge)
                        self.stop.wait(max(0.0, 0.1 - (time.monotonic() - now)))
                        continue
                    self.frame = (picture, info['kegel'], now)
                    self.track_dialog(info, picture, full, dialog_state, now, reading=bool(model))
                    # Stichworte aus den letzten 2 Minuten Dialog (z. B. „Pyro“) gelten immer,
                    # Gemmas Zeigehinweis nur, solange er frisch ist.
                    hint = {'stichworte': [word for stamp, word in self.keywords if now - stamp < 120]}
                    if self.hint and now - self.hint['erfasst'] < 15:
                        hint.update(self.hint, alter=now - self.hint['erfasst'])
                    orders = pilot.tick(info, hint)
                    if not observe:
                        for order in orders:
                            def look(spot=target):
                                if self.stop.is_set() or window() != spot:
                                    raise InterruptedError('Karte pausiert: Stopp oder Spielfokus verloren.')
                                grab = screen.grab(spot[1])
                                return reflexe.verkleinern(
                                    np.frombuffer(grab.rgb, np.uint8).reshape(grab.height, grab.width, 3))
                            if order[0] == 'position':
                                e = pilot.erkunder
                                vorwissen = e.geschaetzte_position() if e is not None else None
                                stand = self.position_bestimmen(look, target, vorwissen)
                                if stand is None and pilot.erkunder is not None:
                                    pilot.erkunder.peilung_fehlgeschlagen()
                                if stand is not None and pilot.erkunder is not None:
                                    pilot.erkunder.kartenstatus(getattr(self, 'kartensymbole', []))
                                    pilot.erkunder.position_neu(*stand)
                                    ziel = pilot.erkunder.ziel
                                    self.messages.put(f'Erkunden: Position {stand[0]:.0f}/{stand[1]:.0f}'
                                                      + (f", Ziel {ziel['typ']} {pilot.erkunder.abstand():.0f} m" if ziel else ''))
                                break
                            if order[0] == 'teleport':
                                if self.teleport(look, target):
                                    self.messages.put('Teleport ausgelöst – Ladebildschirm, danach geht es weiter.')
                                elif getattr(self, 'teleport_fehler', None) == 'karte_zu':
                                    pilot.teleport_bald_wieder()
                                break
                            self.command(order, target)
                    luft = bool(info.get('faellt') or info.get('gleitet'))
                    # Plötzlicher HP-Sturz (Fallschaden): Bildfolge davor sichern.
                    hp = info.get('eigene_hp')
                    hp_sturz = hp is not None and vorher_hp is not None and vorher_hp - hp > .15
                    vorher_hp = hp if hp is not None else vorher_hp
                    risiko = (luft and not vorher_luft) or hp_sturz or any(o[0] == 'ausweichen' for o in orders)
                    if (risiko or self.snapshot) and belege < 6 and now-letzter_beleg > 3:
                        # Bildfolge stammt nur aus bereits aufgenommenen Genshin-Bildern;
                        # Speichern nebenläufig, damit die nächste Rettung nicht auf JPEG wartet.
                        threading.Thread(target=self.save_trace, args=(list(verlauf), pilot.modus),
                                         daemon=True).start()
                        belege += 1
                        letzter_beleg = now
                    vorher_luft = luft
                    if pilot.modus.startswith('kampf') and now - letzter_kampf > 1.0:
                        letzter_kampf = now
                        self.record_combat(picture, info, pilot.modus, orders, now - kampf_start)
                    elif not pilot.modus.startswith('kampf'):
                        kampf_start = now
                    if pilot.modus != last_mode or now - last_report > 10:
                        goal_info = info['ziel']
                        where = f'Questziel {goal_info[0]:.0f}°/{goal_info[1]:.2f}' if goal_info else 'kein Questsymbol'
                        if info.get('raute'):
                            where += f', Raute x={info["raute"][0]:.2f}'
                        if info.get('spur'):
                            where += f', Spur x={info["spur"][0]:.2f}'
                        if info.get('f_hinweis'):
                            where += ', F-Hinweis ' + ('NPC' if info['f_hinweis']['gespraech'] else 'Objekt')
                        if info.get('gleitet') or info.get('faellt'):
                            where += ', Gleiter offen' if info.get('gleitet') else ', Fall erkannt'
                        if info.get('truhe'):
                            where += f', Truhe x={info["truhe"][0]:.2f}'
                        if info.get('pfeile'):
                            where += ', Gegnerpfeile ' + '/'.join(f'{reflexe.pfeil_winkel(*p):+.0f}°' for p in info['pfeile'])
                        if info.get('kampfziel'):
                            where += ', Kampfziel offen'
                        if info.get('q_bereit'):
                            where += ', Q bereit'
                        if info.get('team_q'):
                            where += ', Q bereit bei Platz ' + '/'.join(map(str, info['team_q']))
                        if info.get('eigene_hp') is not None:
                            where += f', HP≈{info["eigene_hp"]:.0%}'
                        camera = f'{info["kegel"]:.0f}°' if info['kegel'] is not None else '?'
                        moving = {True: 'ja', False: 'nein', None: '?'}[info['bewegt']]
                        self.messages.put(f'Reflexe: {pilot.modus} ({where}, Kamera {camera}, bewegt {moving}, '
                                          f'Gegner={"ja" if info["gegner"] else "nein"}, Karte={"ja" if info["hud"] else "nein"}, '
                                          f'Lenkung {pilot.zaehler_pro_grad:.1f}/°)')
                        last_mode, last_report = pilot.modus, now
                    if self.snapshot or now - last_diag > 45:
                        if self.snapshot:
                            ordner = tagesordner(DIAG)
                            Image.fromarray(full).save(ordner / f'F10_{time.strftime("%H%M%S")}.png')
                            self.messages.put(f'F10: Spielbild gespeichert (logs/diag/{ordner.name}).')
                            self.snapshot = False
                        self.save_diag(picture, {**info, 'modus': pilot.modus, 'hint': hint,
                                                 'zaehler_pro_grad': pilot.zaehler_pro_grad}, full)
                        last_diag = now
                    self.stop.wait(max(0.0, 0.12 - (time.monotonic() - now)))
            if self.stop.is_set():
                ending = self.stop_reason or 'Abgebrochen'
        except Exception as error:
            ending = f'{type(error).__name__}: {error}'
        finally:
            self.stop.set()
            for order in pilot.alles_loslassen():
                try:
                    self.command(order, target)
                except Exception:
                    pass
            self.running = False
            self.messages.put('Autopilot beendet: ' + ending)

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
    # Beim Admin-Neustart läuft das alte Panel noch kurz: bis zu 5 s auf dessen Ende warten.
    for attempt in range(50):
        mutex = kernel32.CreateMutexW(None, False, 'Local\\KlausGenshinAgent02')
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() != 183:
            break
        kernel32.CloseHandle(mutex)
        mutex = None
        time.sleep(0.1)
    try:
        if mutex:
            App().root.mainloop()
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)
