"""
Klaus - Rechte: feste Faehigkeiten statt freier Shell. Jede Aktion wird im Vault protokolliert (Aktionen/<Datum>.md),
alles Riskante braucht ein Token aus dem Freigabe-Gate (freigabe.py) - die Funktionen pruefen das selbst.

  Fenster         fenster_liste(), fenster(aktion, titel)               schliessen braucht Freigabe
  Dateien         kopieren(quelle, ziel)                                verschieben/umbenennen brauchen Freigabe
  Programme       programm_suchen(name), programm(aktion, id, token)    winget; installieren/deinstallieren mit Freigabe
  System          lautstaerke(prozent|None), stumm(an), bluetooth(an, token)
  Bildschirm      bildschirmfoto() -> Pfad in Bilder/Klaus
  Zwischenablage  ablage_lesen(), ablage_schreiben(text)

Admin-Rechte bekommt Klaus nie dauerhaft: admin.py startet einzelne, fest hinterlegte Befehle per UAC.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import dateien
import freigabe
import gehirn

KEIN_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def protokoll(text: str) -> None:
    """Jede Aktion landet im Vault: Aktionen/2026-10-05.md"""
    heute = dt.date.today()
    gehirn._anhaengen(gehirn.VAULT / "Aktionen" / f"{heute:%Y-%m-%d}.md",
                      f"---\ntags: [klaus, aktionen]\n---\n# Aktionen {heute:%d.%m.%Y}\n\nWas Klaus am PC getan hat.\n\n",
                      f"- {dt.datetime.now():%H:%M:%S} {text}\n")
    print(f"[Rechte] {text}")


def _ps(befehl: str, timeout: float = 60) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", befehl], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=KEIN_FENSTER)
    if r.returncode != 0 and r.stderr.strip():
        raise RuntimeError(r.stderr.strip().splitlines()[-1][:200])
    return r.stdout.strip()


# ================================================================ Fenster
def fenster_liste() -> list[dict]:
    import win32gui
    import win32process
    import psutil

    aus = []

    def sammeln(h, _):
        if not win32gui.IsWindowVisible(h) or not win32gui.GetWindowText(h).strip():
            return
        if win32gui.GetWindow(h, 4):  # GW_OWNER: Unterfenster/Dialoge auslassen
            return
        _, pid = win32process.GetWindowThreadProcessId(h)
        try:
            prog = psutil.Process(pid).name()
        except psutil.Error:
            prog = "?"
        if prog.lower() in ("pythonw.exe", "textinputhost.exe", "applicationframehost.exe") and "Klaus" not in win32gui.GetWindowText(h):
            return
        aus.append({"hwnd": h, "titel": win32gui.GetWindowText(h)[:90], "programm": prog})

    win32gui.EnumWindows(sammeln, None)
    return aus


def _finde_fenster(titel: str) -> dict:
    such = titel.lower().strip()
    treffer = [f for f in fenster_liste() if such in f["titel"].lower() or such in f["programm"].lower()]
    if not treffer:
        raise LookupError(f"Kein Fenster mit „{titel}“ gefunden.")
    return treffer[0]


def fenster(aktion: str, titel: str, token: str | None = None) -> str:
    """aktion: fokus | minimieren | maximieren | wiederherstellen | links | rechts | schliessen (Freigabe)"""
    import win32api
    import win32con
    import win32gui

    f = _finde_fenster(titel)
    h = f["hwnd"]
    if aktion == "schliessen":
        freigabe.pruefe(token, "fenster_schliessen")  # ungespeicherte Arbeit koennte verloren gehen
        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
    elif aktion == "minimieren":
        win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
    elif aktion == "maximieren":
        win32gui.ShowWindow(h, win32con.SW_MAXIMIZE)
    elif aktion == "wiederherstellen":
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
    elif aktion in ("links", "rechts"):
        mon = win32api.GetMonitorInfo(win32api.MonitorFromWindow(h, 2))["Work"]  # Arbeitsflaeche ohne Taskleiste
        b = (mon[2] - mon[0]) // 2
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
        win32gui.MoveWindow(h, mon[0] + (0 if aktion == "links" else b), mon[1], b, mon[3] - mon[1], True)
    elif aktion == "fokus":
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(h)
        except Exception:  # Windows erlaubt Vordergrund nur unter Bedingungen - Alt-Trick
            win32api.keybd_event(0x12, 0, 0, 0)
            win32gui.SetForegroundWindow(h)
            win32api.keybd_event(0x12, 0, 2, 0)
    else:
        raise ValueError(f"Unbekannte Fenster-Aktion: {aktion}")
    protokoll(f"Fenster {aktion}: {f['titel']} ({f['programm']})")
    return f"{f['titel'][:50]}: {aktion}."


# ================================================================ Dateien
def _pfad_ok(pfad: Path, was: str) -> None:
    if not dateien.erlaubt(pfad):
        raise PermissionError(f"{was}: geschützter Ort ({pfad})")


def kopieren(quelle: str, ziel: str) -> str:
    q, z = Path(quelle), Path(ziel)
    if not q.exists():
        raise FileNotFoundError(quelle)
    _pfad_ok(z if z.exists() else z.parent, "Kopieren")
    ziel_pfad = z / q.name if z.is_dir() else z
    if ziel_pfad.exists():
        raise FileExistsError(f"Gibt es schon: {ziel_pfad}")
    (shutil.copytree if q.is_dir() else shutil.copy2)(q, ziel_pfad)
    protokoll(f"Kopiert: {q} -> {ziel_pfad}")
    return f"{q.name} ist nach {ziel_pfad.parent} kopiert."


def verschieben(quelle: str, ziel: str, token: str | None) -> str:
    """Verschieben/Umbenennen (ziel = neuer Name im selben Ordner oder Zielordner) - nur mit Freigabe."""
    q, z = Path(quelle), Path(ziel)
    if not q.exists():
        raise FileNotFoundError(quelle)
    if not z.is_absolute():
        z = q.parent / z  # nur ein neuer Name -> umbenennen
    _pfad_ok(q, "Verschieben")
    _pfad_ok(z if z.exists() else z.parent, "Verschieben")
    ziel_pfad = z / q.name if z.is_dir() else z
    if ziel_pfad.exists():
        raise FileExistsError(f"Gibt es schon: {ziel_pfad}")
    freigabe.pruefe(token, "verschieben")
    shutil.move(str(q), str(ziel_pfad))
    protokoll(f"Verschoben: {q} -> {ziel_pfad}")
    return f"{q.name} heißt/liegt jetzt: {ziel_pfad}."


# ================================================================ Programme (winget)
def programm_suchen(name: str) -> list[dict]:
    r = subprocess.run(["winget", "search", name, "--accept-source-agreements", "--disable-interactivity"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=90, creationflags=KEIN_FENSTER)
    zeilen = [z for z in r.stdout.splitlines() if z.strip()]
    kopf = next((i for i, z in enumerate(zeilen) if z.lstrip().startswith("Name") and " ID" in z), None)
    if kopf is None:
        return []
    k = zeilen[kopf]
    a_id, a_ver = k.index(" ID") + 1, k.index(" Version") + 1 if " Version" in k else None
    aus = []
    for z in zeilen[kopf + 2: kopf + 10]:
        name_ = z[:a_id].strip()
        rest = z[a_id:].split()
        if rest:
            aus.append({"name": name_, "id": rest[0], "version": z[a_ver:].split()[0] if a_ver and len(z) > a_ver else ""})
    return aus


def programm(aktion: str, paket_id: str, token: str | None) -> str:
    """installieren | deinstallieren | aktualisieren - immer mit Freigabe; der Installer fragt selbst per UAC nach Adminrechten."""
    befehl = {"installieren": "install", "deinstallieren": "uninstall", "aktualisieren": "upgrade"}.get(aktion)
    if not befehl:
        raise ValueError(f"Unbekannte Programm-Aktion: {aktion}")
    freigabe.pruefe(token, "programm")
    args = ["winget", befehl, "--id", paket_id, "-e", "--silent", "--disable-interactivity"]
    if befehl != "uninstall":
        args += ["--accept-package-agreements", "--accept-source-agreements"]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800, creationflags=KEIN_FENSTER)
    ok = r.returncode == 0
    protokoll(f"Programm {aktion}: {paket_id} -> {'ok' if ok else 'Fehler ' + str(r.returncode)}")
    letzte = [z for z in r.stdout.splitlines() if z.strip()][-1:] or [""]
    return f"{paket_id}: {'erledigt' if ok else 'hat nicht geklappt'} ({letzte[0].strip()[:80]})."


# ================================================================ System
def _lautsprecher():
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def lautstaerke(prozent: float | None = None) -> str:
    v = _lautsprecher()
    if prozent is not None:
        v.SetMasterVolumeLevelScalar(max(0.0, min(1.0, prozent / 100)), None)
        protokoll(f"Lautstärke {round(prozent)} %")
    return f"Lautstärke {round(v.GetMasterVolumeLevelScalar() * 100)} Prozent."


def stumm(an: bool) -> str:
    _lautsprecher().SetMute(1 if an else 0, None)
    protokoll(f"Ton {'aus' if an else 'an'}")
    return "Ton aus." if an else "Ton an."


def bluetooth(an: bool, token: str | None) -> str:
    """Bluetooth-Funk an/aus (Windows.Devices.Radios). Ausschalten trennt Kopfhoerer/Maus -> Freigabe."""
    if not an:
        freigabe.pruefe(token, "bluetooth")
    skript = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$warte = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function W($op, $typ) { $t = $warte.MakeGenericMethod($typ).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
W ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = W ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | ? { $_.Kind -eq 'Bluetooth' }
if (-not $bt) { 'KEIN'; exit }
W ($bt.SetStateAsync('ZIEL')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$bt.State
""".replace("ZIEL", "On" if an else "Off")
    ergebnis = _ps(skript, timeout=40)
    if "KEIN" in ergebnis:
        return "Ich finde keinen Bluetooth-Adapter."
    protokoll(f"Bluetooth {'an' if an else 'aus'}")
    return f"Bluetooth ist {'an' if an else 'aus'}."


# ================================================================ Bildschirm + Zwischenablage
def bildschirmfoto() -> str:
    ordner = Path.home() / "Pictures" / "Klaus"
    ordner.mkdir(parents=True, exist_ok=True)
    datei = ordner / f"Bildschirm_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    _ps("Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
        "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; $g=[System.Drawing.Graphics]::FromImage($bmp); "
        f"$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); $bmp.Save('{datei}'); $g.Dispose(); $bmp.Dispose()")
    protokoll(f"Bildschirmfoto: {datei}")
    return str(datei)


def ablage_lesen() -> str:
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) if win32clipboard.IsClipboardFormatAvailable(13) else ""
    finally:
        win32clipboard.CloseClipboard()
    protokoll(f"Zwischenablage gelesen ({len(text)} Zeichen)")
    return text[:4000]


def ablage_schreiben(text: str) -> str:
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    protokoll(f"Zwischenablage beschrieben ({len(text)} Zeichen)")
    return "Steht in der Zwischenablage."


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print("Programme mit Fenster:", sorted({f["programm"] for f in fenster_liste()}))  # Titel nicht ausgeben (privat)
    print(lautstaerke())
