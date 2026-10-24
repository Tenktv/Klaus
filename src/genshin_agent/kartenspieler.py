"""Den eigenen cyanfarbenen Spielerpfeil auf der Weltkarte erkennen."""
import numpy as np

import reflexe


def _flecken(maske):
    """Zusammenhängende Farbflächen mit vier Nachbarn, ohne OpenCV-Abhängigkeit."""
    ys, xs = np.nonzero(maske)
    offen = set(zip(ys.tolist(), xs.tolist()))
    while offen:
        punkt = offen.pop()
        stapel, flaeche = [punkt], [punkt]
        while stapel:
            y, x = stapel.pop()
            for nachbar in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if nachbar in offen:
                    offen.remove(nachbar)
                    stapel.append(nachbar)
                    flaeche.append(nachbar)
        yield np.asarray(flaeche)


def spieler(picture):
    """``(x, y, Güte)`` relativ zum aktuellen Bild, bei Unsicherheit ``None``.

    Der gefüllte, sattcyanfarbene Pfeil ist größer als die cyanfarbenen Kerne
    freier Wegpunkte. Ein rotationsunabhängiges drittes Flächenmoment prüft seine
    dreieckige Form; Kreise, Rauten und Rechtecke bestehen diese Prüfung nicht.
    Mehrere passende Pfeile werden ausdrücklich nicht nach Bildschirmmitte sortiert.
    """
    if picture.ndim != 3 or picture.shape[2] < 3 or min(picture.shape[:2]) < 40:
        return None
    if not reflexe.karte_offen(picture):
        return None
    hoehe, breite = picture.shape[:2]
    k = hoehe / 540
    rgb = picture[..., :3].astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    cyan = ((r < 90) & (g > 145) & (b > 170) & (g-r > 95)
            & (b-r > 120) & (np.abs(b-g) < 85))
    cyan[:round(.1 * hoehe)] = False
    cyan[round(.92 * hoehe):] = False
    cyan[:round(.31 * hoehe), :round(.2 * breite)] = False
    kandidaten = []
    for flaeche in _flecken(cyan):
        n = len(flaeche)
        if not 75 * k*k <= n <= 320 * k*k:
            continue
        ys, xs = flaeche.T
        w, h = np.ptp(xs) + 1, np.ptp(ys) + 1
        if not (10*k <= w <= 28*k and 10*k <= h <= 28*k):
            continue
        if not .38 <= n / (w*h) <= .82:
            continue
        z = (xs - xs.mean()) + 1j * (ys - ys.mean())
        radius2 = np.mean(np.abs(z)**2)
        if radius2 <= 0:
            continue
        dreieck = abs(np.mean(z**3)) / radius2**1.5
        eigenwerte = np.linalg.eigvalsh(np.cov(flaeche.T))
        if eigenwerte[0] <= 0 or eigenwerte[-1] / eigenwerte[0] > 2.6:
            continue
        if not .38 <= dreieck <= 1.05:
            continue
        guete = float(min(.99, .75 + .24 * min(1, dreieck/.65)))
        kandidaten.append((float(xs.mean()/breite), float(ys.mean()/hoehe), guete))
    return kandidaten[0] if len(kandidaten) == 1 else None
