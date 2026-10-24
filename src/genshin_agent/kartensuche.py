"""Begrenzte Suche auf der sichtbaren Weltkarte, ohne eigene Eingabe-API.

Jede Kartenbewegung endet mit einer neuen Aufnahme. Die aufrufende Anwendung
prüft Fokus und Stoppwunsch in ``command``; dieser Code bestätigt keinen Teleport.
"""
import math
import time

import reflexe
import kartenatlas
import kartenspieler


MAX_SEKUNDEN = 60.0
MAX_RASTERANSICHTEN = 25
MAX_ZOOM_RAUS = 3
MAX_ZOOM_REIN = 3
ZOOM_RASTEN = 12     # Mausrad-Rastungen je Zoomschritt (eine allein: ~2 % Maßstab)
NAH = .06            # Wegpunkt so nah am Questsymbol (Bildhöhen): kein Heranzoomen nötig
MITTE = (.51, .5)


def kandidaten(picture, quest):
    """Freie Ziele nah an der Quest; alternativ weiter weg, wenn das Weg spart."""
    if quest is None:
        return []
    qx, qy = quest[:2]
    seitenverhaeltnis = picture.shape[1] / picture.shape[0]

    def abstand(punkt):
        return math.hypot((punkt['x'] - qx) * seitenverhaeltnis, punkt['y'] - qy)

    freie = [p for p in reflexe.teleportziele(picture) if p['offen']]
    if not freie:
        return []
    nahe = sorted((p for p in freie if abstand(p) < .25), key=abstand)
    if nahe:
        return nahe
    # Ohne eindeutigen Spielerpfeil lässt sich eine Reiseersparnis nicht belegen.
    # Im Atlas bekannte Punkte sind keine Freischaltungsnachweise.
    eigen = kartenspieler.spieler(picture)
    if eigen is None:
        return []
    bisher = math.hypot((eigen[0]-qx)*seitenverhaeltnis, eigen[1]-qy)
    if bisher < .05:
        return []
    return sorted((dict(p, weg_ersparnis=1-abstand(p)/bisher) for p in freie
                   if abstand(p) < .8*bisher), key=abstand)


def _spirale():
    """Die 25 Nachbarfelder eines 5×5-Rasters, von der Mitte aus."""
    x = y = 0
    yield x, y
    schritte = 1
    richtungen = ((1, 0), (0, 1), (-1, 0), (0, -1))
    richtung = 0
    while schritte <= 5:
        for _ in range(2):
            dx, dy = richtungen[richtung % 4]
            richtung += 1
            for _ in range(schritte):
                x, y = x + dx, y + dy
                if abs(x) <= 2 and abs(y) <= 2:
                    yield x, y
        schritte += 1


class _Suche:
    def __init__(self, picture, look, command, melden, diagnose):
        self.bild = picture
        self.look = look
        self.command = command
        self.melden = melden
        self.diagnose = diagnose
        self.ende = time.monotonic() + MAX_SEKUNDEN
        self.zoom = 0
        self.quest = None
        self.rand = None
        self.kandidaten = []
        self.aktiv = True

    def auswerten(self, schritt):
        if time.monotonic() >= self.ende or not reflexe.karte_offen(self.bild):
            self.aktiv = False
            self.quest, self.rand, self.kandidaten = None, None, []
            return False
        self.quest = reflexe.raute(self.bild, weltkarte=True)
        # Goldenes Randsymbol = Ziel außerhalb des Ausschnitts, nicht das Ziel selbst.
        self.rand = reflexe.quest_randmarker(self.bild)
        if self.quest is not None and self.rand is not None and \
                math.hypot(self.quest[0] - self.rand[0], self.quest[1] - self.rand[1]) < .04:
            self.quest = None
        self.kandidaten = kandidaten(self.bild, self.quest)
        if self.diagnose is not None:
            self.diagnose(self.bild, {'schritt': schritt, 'zoom': self.zoom, 'quest': self.quest,
                                    'rand': self.rand, 'kandidaten': len(self.kandidaten)})
        return True

    def bewegen(self, befehl, schritt, warten=.7):
        # Aufnahmen und Eingaben bleiben strikt abwechselnd. Insbesondere werden
        # nach einem nicht ausgeführten Befehl keine alten Treffer zurückgegeben.
        if not self.aktiv or time.monotonic() >= self.ende:
            self.aktiv = False
            return False
        if not self.command(befehl) or not self.command(('warten', warten)):
            self.aktiv = False
            return False
        self.bild = self.look()
        return self.auswerten(schritt)

    def zoomen(self, richtung):
        self.zoom += richtung
        return self.bewegen(('karte_zoom', richtung * ZOOM_RASTEN), 'rauszoomen' if richtung < 0 else 'detailzoom',
                            warten=1.0)

    def naechster_abstand(self):
        if self.quest is None or not self.kandidaten:
            return None
        h, w = self.bild.shape[:2]
        k = self.kandidaten[0]
        return math.hypot((k['x'] - self.quest[0]) * w / h, k['y'] - self.quest[1])

    def naeher_ran(self):
        """Bestes Ziel weit vom Questsymbol: Quest zentrieren und schrittweise hineinzoomen –
        Städte zeigen ihre Wegpunkte erst dann (Livelauf 23:18: Statue in Vissudha statt eines
        Wegpunkts in Sumeru-Stadt, danach Klettern und Fallschaden). Verschwinden beim Zoomen
        alle Ziele aus dem Umkreis, eine Stufe zurück."""
        for _ in range(MAX_ZOOM_REIN):
            abstand = self.naechster_abstand()
            if abstand is None or abstand <= NAH:
                return True
            if not self.zentrieren() or not self.zoomen(1):
                return False
            if not self.kandidaten:
                return self.zoomen(-1)
        return True

    def zentrieren(self):
        if self.quest is None:
            return True
        qx, qy = self.quest[:2]
        return self.verschieben_zu(qx, qy, 'quest_zentrieren')

    def verschieben_zu(self, qx, qy, schritt):
        dx, dy = MITTE[0] - qx, MITTE[1] - qy
        if abs(dx) < .06 and abs(dy) < .06:
            return True
        # Der Questmarker selbst kann auf einem Randpfeil liegen. Die Ziehgeste
        # startet deshalb in freier Kartenfläche und verschiebt um denselben Weg.
        dx, dy = max(-.6, min(.6, dx)), max(-.73, min(.73, dy))
        x0, y0 = MITTE[0] - dx / 2, .485 - dy / 2
        x1, y1 = MITTE[0] + dx / 2, .485 + dy / 2
        return self.bewegen(('karte_ziehen', x0, y0, x1, y1), schritt)

    def atlas_pruefen(self):
        """Bekannte öffentliche Positionen helfen nur beim Suchen, nie beim Klicken.

        Erst mehrere passende Symbole verankern den Atlas im aktuellen Bild.
        Freischaltungen werden ausschließlich aus dem frischen Spielbild gelesen.
        """
        try:
            transform = kartenatlas.lokalisieren(self.bild)
        except (OSError, ValueError, KeyError):
            self.melden('Kartenatlas nicht verfügbar – suche anhand der Spielbilder weiter.')
            return True
        if transform is None:
            return True
        self.melden(f'Kartenatlas: {transform["treffer"]} Symbole zugeordnet '
                    f'(Abweichung {transform["fehler"]:.1f} Pixel).')
        if self.diagnose is not None:
            self.diagnose(self.bild, {'schritt': 'atlas_abgleich', 'atlas': transform})
        if self.quest is None or self.kandidaten:
            return True
        h, w = self.bild.shape[:2]
        qx, qy = self.quest[:2]
        for punkt in kartenatlas.naechstgelegene(qx, qy, transform, w, h, anzahl=12):
            x = (transform['scale']*punkt['x_pos'] + transform['offset_x']) / w
            y = (transform['scale']*transform['y_sign']*punkt['y_pos'] + transform['offset_y']) / h
            # Sichtbare gesperrte Punkte nicht erneut probieren. Ein naher Punkt
            # außerhalb der freien Kartenfläche kann durch Zentrieren auftauchen.
            if .20 <= x <= .82 and .12 <= y <= .85:
                continue
            if math.hypot((x-qx)*w/h, y-qy) > .65:
                continue  # weiter entfernte Atlasziele brauchen erst Überblick/Zoom
            mitte_x, mitte_y = (x+qx)/2, (y+qy)/2
            if abs(mitte_x-MITTE[0]) < .06 and abs(mitte_y-MITTE[1]) < .06:
                continue
            self.melden('Kartenatlas: angrenzendes Teleportziel suchen; Freischaltung im Spiel prüfen.')
            return self.verschieben_zu(mitte_x, mitte_y, 'atlas_suchbereich')
        return True

    def detail_pruefen(self):
        if not self.zentrieren():
            return False
        while self.zoom < 0:
            if not self.zoomen(1):
                return False
        return True

    def ueberblick(self):
        while self.zoom > -MAX_ZOOM_RAUS:
            if not self.zoomen(-1):
                return False
            if self.kandidaten:
                return True
        return True

    def ergebnis(self):
        if not self.aktiv:
            return self.bild, None, []
        return self.bild, self.quest, self.kandidaten


def suchen(picture, look, command, melden, diagnose=None):
    """Quest und freigeschaltete Teleportziele auf frischen Bildern suchen.

    ``command(tuple)`` muss bei Stopp/Fokusverlust ``False`` liefern. Alle
    Koordinaten sind relativ zum Spielbild. Exceptions (auch Unterbrechungen)
    bleiben beim Aufrufer. Die Suche endet spätestens nach 60 Sekunden vor der
    nächsten Eingabe; ein bereits laufender Aufnahme-Callback muss selbst enden.
    """
    suche = _Suche(picture, look, command, melden, diagnose)
    if not suche.auswerten('start'):
        return suche.ergebnis()
    # Ziel in einer anderen Region (Inazuma -> Großer Basar, 7 km): Raster und Zoom finden es nie.
    # Ein Klick auf das goldene Randsymbol lässt die Karte zum Ziel springen (Nikola, 23:02).
    for _ in range(2):
        if suche.quest is not None or suche.rand is None:
            break
        melden('Kartensuche: Questziel außerhalb – goldenes Randsymbol anklicken, die Karte springt hin.')
        if not suche.bewegen(('maus_klick', suche.rand[0], suche.rand[1]), 'randsymbol', warten=1.5):
            return suche.ergebnis()
    if not suche.atlas_pruefen():
        return suche.ergebnis()
    if suche.quest is not None:
        qx, qy = suche.quest[:2]
        am_rand = qx < .2 or qx > .8 or qy < .18 or qy > .82
        if am_rand or not suche.kandidaten:
            melden('Kartensuche: Questziel in die Kartenmitte holen.')
            if not suche.zentrieren():
                return suche.ergebnis()
        if suche.kandidaten:
            if (suche.naechster_abstand() or 0) > NAH:
                melden('Kartensuche: nächster Wegpunkt weit vom Ziel – hineinzoomen (Städte zeigen mehr).')
                suche.naeher_ran()
            return suche.ergebnis()

    # Ein schon im ursprünglichen Detailgrad sichtbares Ziel wurde damit bereits
    # geprüft. Es muss nicht nach jeder kleinen Kartenbewegung erneut gesucht werden.
    detail_geprueft = suche.quest is not None
    melden('Kartensuche: herauszoomen und weitere Teleportziele prüfen.')
    for _ in range(MAX_ZOOM_RAUS):
        if not suche.zoomen(-1):
            return suche.ergebnis()
        if suche.kandidaten:
            if not suche.zentrieren():
                return suche.ergebnis()
            if suche.kandidaten:
                return suche.ergebnis()
        if suche.quest is not None and not detail_geprueft:
            melden('Kartensuche: Quest gefunden, Teleportziele im Detail prüfen.')
            if not suche.detail_pruefen():
                return suche.ergebnis()
            detail_geprueft = True
            if suche.kandidaten:
                return suche.ergebnis()
            break
    if not suche.ueberblick() or suche.kandidaten:
        return suche.ergebnis()

    melden('Kartensuche: benachbarte Kartenausschnitte systematisch absuchen (max. 25).')
    ansichten = 1
    raster = iter(_spirale())
    vorher = next(raster)
    while ansichten < MAX_RASTERANSICHTEN:
        feld = next(raster, None)
        if feld is None:
            break
        dx, dy = feld[0] - vorher[0], feld[1] - vorher[1]
        vorher = feld
        befehl = ('karte_ziehen', MITTE[0] + .225 * dx, .5 + .2 * dy,
                  MITTE[0] - .225 * dx, .5 - .2 * dy)
        if not suche.bewegen(befehl, 'kartenausschnitt'):
            return suche.ergebnis()
        ansichten += 1
        if suche.kandidaten:
            vor_zentrieren = suche.bild
            if not suche.zentrieren():
                return suche.ergebnis()
            if suche.kandidaten:
                return suche.ergebnis()
            if suche.bild is not vor_zentrieren:
                raster = iter(_spirale())
                vorher = next(raster)
        if suche.quest is not None and not detail_geprueft:
            melden('Kartensuche: Quest gefunden, zurück zum Detailgrad.')
            if not suche.detail_pruefen():
                return suche.ergebnis()
            detail_geprueft = True
            if suche.kandidaten:
                return suche.ergebnis()
            if not suche.ueberblick() or suche.kandidaten:
                return suche.ergebnis()
            # Zentrieren/Zoomen ändert den Rasterursprung. Der nächste Schritt
            # beginnt deshalb von der neuen Mitte; das Gesamtlimit bleibt bestehen.
            raster = iter(_spirale())
            vorher = next(raster)
        if ansichten % 5 == 0:
            melden(f'Kartensuche: {ansichten}/{MAX_RASTERANSICHTEN} Ausschnitte geprüft.')
    melden('Kartensuche beendet: kein geeigneter freigeschalteter Teleport im Suchbereich.')
    return suche.ergebnis()
