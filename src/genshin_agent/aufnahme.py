"""Kalibrier-Aufnahme für Claude: speichert Menü-, Karten- und Questbuch-Bilder in voller Größe.

Nur wenn Genshin im Vordergrund ist und kein normales Spielbild (HUD) zu sehen ist; sendet keine
Eingaben. Ein neues Bild nur, wenn es sich deutlich vom letzten unterscheidet (höchstens 60).
Aufruf: python aufnahme.py [sekunden=300]  → logs/aufnahme/
"""
from pathlib import Path
import sys
import time

import mss
import numpy as np
from PIL import Image

import reflexe
from app import window  # Fokusprüfung: nur GenshinImpact.exe / YuanShen.exe

ZIEL = Path(__file__).resolve().parent / 'logs' / 'aufnahme'


def main(dauer=300):
    ZIEL.mkdir(parents=True, exist_ok=True)
    ende = time.monotonic() + dauer
    letzte, anzahl = None, 0
    with mss.mss() as screen:
        while time.monotonic() < ende and anzahl < 60:
            spiel = window()
            if spiel:
                shot = screen.grab(spiel[1])
                voll = np.frombuffer(shot.rgb, np.uint8).reshape(shot.height, shot.width, 3)
                klein = reflexe.verkleinern(voll)
                if not reflexe.hud_sichtbar(voll, klein):
                    signatur = klein[::8, ::8].astype(np.float32)
                    if letzte is None or float(np.abs(signatur - letzte).mean()) > 6:
                        name = f'{time.strftime("%H%M%S")}_{anzahl:02d}.jpg'
                        Image.fromarray(voll).save(ZIEL / name, quality=95)
                        letzte, anzahl = signatur, anzahl + 1
                        print('gespeichert', name, flush=True)
            time.sleep(0.7)
    print('fertig,', anzahl, 'Bilder', flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
