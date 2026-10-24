"""Erkundungsmodus: Truhen, Okuli, gesperrte Teleportpunkte/Statuen und Domänen ansteuern.

Position: nur bei offener Karte bekannt (Atlas-Abgleich + Spielerpfeil, 1 Atlaseinheit = 1 m,
gemessen 6977 Einheiten für „6986m“). Dazwischen Koppelnavigation: Kompasskurs aus der letzten
Position, zurückgelegter Weg = gelaufene Zeit × gelernte Geschwindigkeit. Erledigte Ziele stehen in
logs/erkundet.json – auch solche, die schon vorher geöffnet waren (vor Ort nichts gefunden).
Die Karte ist genordet; Kurs 0° = Norden, im Uhrzeigersinn, wie der Sichtkegel der Minimap.
Teleportpunkte und Statuen: Jeder Kartenblick zeigt sie grau (gesperrt) oder blau (frei) – nur
gesperrte werden angesteuert. Wegpunkte und Domänen schalten sich beim Annähern frei, Statuen per F.
"""
import json
import math
import re
from pathlib import Path
import time

import raetsel_db

DATEI = Path(__file__).with_name('logs') / 'erkundet.json'
ANKUNFT = 8.0           # m laut Kartenpeilung (Genauigkeit ~5 m): letzte Meter + Suche
NEU_PEILEN = 25.0       # s Laufzeit, danach Position auf der Karte erneuern
REICHWEITE = 400.0      # m: weiter entfernte Ziele erst nach einem Teleport (spätere Stufe)
ZIEL_ZEIT = 150.0       # s je Ziel, dann „unerreichbar“
STANDARD_ARTEN = ('truhe', 'sammeln', 'teleport', 'statue', 'domaene')
NUR_GESPERRT = ('teleport', 'statue')   # Freischaltstatus von der Karte bekannt
ZUORDNUNG = 25.0        # m: Kartensymbol gehört zu diesem Atlaspunkt
# Okuli: Viele liegen hoch, schweben, brauchen Spezialmechanik oder sind hinter Quests/Rätseln
# (Nikola: „ein paar sind Rätsel oder sehr hoch, wo man kreativ sein muss“). Der Community-
# Hinweis verrät das meist; solche Ziele bleiben für Claude (F11) statt für den Autopiloten.
# Nicht als schwer: „under/below/inside/enter“ (Under the bridge, below its trunk, Enter through
# the door) – geprüft an 800 echten Hinweisen; „high“ nur als Wort (nicht „highway“).
SCHWER = re.compile(r"\b(top|above|mid-?air|float|roof|tower|cliff|peak|summit|high\b|highest|climb|glid|jump|"
                    r"mountain|steeple|structure|launch|kuuhenki|moonlane|kuuvahki|grapple|ride|wind current|"
                    r"updraft|four-leaf|sigil|granum|seelie|qucusaur|saurian|construct|mist|warp|unipolar|"
                    r"bipolar|transform|quest|cave|underground|underwater|dive|domain|barrier|locked|hidden|"
                    r"puzzle|challenge|complet|mechanism|chamber|accessible|after|prim(e|al) ice|melt)", re.I)


def schwer(punkt):
    """Okulus mit Hinweis auf Höhe, Spezialmechanik oder Zugangssperre (Truhen haben keine Hinweise)."""
    return punkt['art'] == 'sammeln' and bool(SCHWER.search(punkt.get('hinweis') or ''))


class Erkunder:
    def __init__(self, arten=STANDARD_ARTEN, datei=DATEI, uhr=time.monotonic, nur_leichte=True):
        self.arten = tuple(arten)
        self.nur_leichte = nur_leichte
        self.datei = Path(datei)
        self.uhr = uhr
        try:
            self.erledigt = json.loads(self.datei.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.erledigt = {}
        self.fix = None            # (x, y, y_sign, zeit) der letzten Kartenposition
        self.gelaufen = 0.0        # s mit W seit der letzten Position
        self.geschwindigkeit = 5.5  # m/s, wird zwischen zwei Positionen nachgelernt
        self.ziel = None
        self.ziel_seit = None
        self.ankunft_bestaetigt = False
        self.ziel_dauer = 0.0
        self.peilung_pause_bis = -1e9
        self.versuche = {}
        self.gesperrt = set()     # Atlas-Ids grau gesehener Teleportpunkte/Statuen

    # --- Position ---------------------------------------------------------------

    def position_neu(self, x, y, y_sign=1.0):
        jetzt = self.uhr()
        if self.fix is not None and self.gelaufen > 4:
            gemessen = math.hypot(x - self.fix[0], y - self.fix[1]) / self.gelaufen
            if 2 <= gemessen <= 12:  # Ausreißer (Hindernis, Teleport) nicht lernen
                self.geschwindigkeit = .7 * self.geschwindigkeit + .3 * gemessen
        self.fix = (x, y, y_sign, jetzt)
        self.gelaufen = 0.0
        # Ankunft gilt nur mit Kartenbeweis – nicht nach Schätzung (Livelauf 22:29: „am Ziel“
        # bei noch 17 m, Suche an der falschen Stelle, Okulus abgehakt).
        self.ankunft_bestaetigt = self.ziel is not None and self.abstand() <= ANKUNFT

    def geschaetzte_position(self):
        """(x, y, y_sign): letzte Peilung plus gelaufener Weg Richtung Ziel – Vorwissen für die
        Positionsbestimmung in Gegenden mit wenigen Kartensymbolen."""
        if self.fix is None:
            return None
        x, y, y_sign, _ = self.fix
        if self.ziel is not None and self.gelaufen > 0:
            dx, dy = self.ziel['x_pos'] - x, self.ziel['y_pos'] - y
            gerade = math.hypot(dx, dy)
            if gerade > 0:
                anteil = min(1.0, self.gelaufen * self.geschwindigkeit / gerade)
                x, y = x + dx * anteil, y + dy * anteil
        return x, y, y_sign

    def laufen(self, sekunden):
        self.gelaufen += max(0.0, sekunden)

    def peilung_noetig(self):
        """Neue Kartenposition nötig: keine Position, 25 s gelaufen, oder geschätzte Ankunft ohne
        Kartenbeweis. Ist die Ankunft bestätigt, stört die Suche vor Ort nicht mehr."""
        if self.uhr() < self.peilung_pause_bis:
            return False
        if self.fix is None:
            return True
        if self.ankunft_bestaetigt:
            return False
        rest = self.abstand()
        if rest is not None and rest <= ANKUNFT:
            return True
        return self.gelaufen >= NEU_PEILEN

    # --- Ziele ------------------------------------------------------------------

    def ziel_waehlen(self):
        """Nächstes unerledigtes Ziel (oberirdisch) um die letzte Position, oder None."""
        self.ziel = self.ziel_seit = None
        self.ankunft_bestaetigt = False
        self.ziel_dauer = 0.0
        if self.fix is None:
            return None
        kandidaten = [p for p in raetsel_db.in_der_naehe(self.fix[0], self.fix[1], radius=REICHWEITE, anzahl=600)
                      if p['art'] in self.arten and p.get('z_level', 0) == 0 and str(p['id']) not in self.erledigt
                      and (p['art'] not in NUR_GESPERRT or p['id'] in self.gesperrt)
                      and not (self.nur_leichte and schwer(p))]
        if kandidaten:
            self.ziel = kandidaten[0]
            self.ziel_seit = self.uhr()
            # Direkt nach einer Peilung gewählt und schon nah: Das ist ein Kartenbeweis.
            self.ankunft_bestaetigt = self.gelaufen <= 1.0 and self.abstand() <= ANKUNFT
        return self.ziel

    def kartenstatus(self, symbole):
        """Sichtbare Wegpunkt-/Statuensymbole eines Kartenblicks: [(x, y, offen, art)] in Atlas-Metern,
        art 'wegpunkt' oder 'statue'. Blau = schon frei (abhaken), grau = Ziel. Ist ein besuchter
        Punkt noch grau, gibt es einen zweiten Versuch."""
        arten = {'wegpunkt': 'teleport', 'statue': 'statue'}
        for x, y, offen, art in symbole:
            naehe = raetsel_db.in_der_naehe(x, y, radius=ZUORDNUNG, anzahl=1, art=arten.get(art))
            if not naehe:
                continue
            punkt_id = naehe[0]['id']
            eintrag = self.erledigt.get(str(punkt_id))
            if offen:
                self.gesperrt.discard(punkt_id)
                if eintrag is None or eintrag['grund'] == 'besucht':
                    self.erledigt[str(punkt_id)] = {'typ': naehe[0]['typ'], 'grund': 'schon frei' if eintrag is None
                                                    else 'freigeschaltet', 'zeit': time.strftime('%Y-%m-%d %H:%M:%S')}
            else:
                self.gesperrt.add(punkt_id)
                if eintrag is not None and eintrag['grund'] == 'besucht' and eintrag.get('versuche', 1) < 2:
                    del self.erledigt[str(punkt_id)]  # noch grau: ein zweiter Versuch
                    self.versuche[punkt_id] = eintrag.get('versuche', 1) + 1
        self._speichern()

    def kurs(self):
        """Kompasskurs vom geschätzten Standort zum Ziel (0° = Norden, im Uhrzeigersinn)."""
        if self.fix is None or self.ziel is None:
            return None
        dx = self.ziel['x_pos'] - self.fix[0]
        dy = self.ziel['y_pos'] - self.fix[1]
        return math.degrees(math.atan2(dx, -self.fix[2] * dy)) % 360

    def abstand(self):
        """Geschätzte Reststrecke in m (Luftlinie minus seit der Peilung gelaufener Weg)."""
        if self.fix is None or self.ziel is None:
            return None
        gerade = math.hypot(self.ziel['x_pos'] - self.fix[0], self.ziel['y_pos'] - self.fix[1])
        return max(0.0, gerade - self.gelaufen * self.geschwindigkeit)

    def unterwegs(self, sekunden):
        """Zeit im Erkundungsmodus (nicht im Kampf) zählt gegen die Zielgrenze."""
        if self.ziel is not None:
            self.ziel_dauer += max(0.0, sekunden)

    def ziel_abgelaufen(self):
        """150 s Erkundungszeit ohne Ankunft – Kämpfe unterwegs zählen nicht (Livelauf 22:39: Truhe
        nach vielen Kämpfen als unerreichbar abgehakt)."""
        return self.ziel is not None and self.ziel_dauer > ZIEL_ZEIT

    def peilung_fehlgeschlagen(self):
        """Karte ohne sichere Position (Höhle, Untergrund-Ebene): 15 s weiterlaufen statt alle 4 s
        erneut die Karte zu öffnen."""
        self.peilung_pause_bis = self.uhr() + 15

    def erledigen(self, grund):
        """Ziel abhaken (geöffnet, nichts gefunden, unerreichbar) und dauerhaft merken."""
        if self.ziel is None:
            return
        self.erledigt[str(self.ziel['id'])] = {'typ': self.ziel['typ'], 'grund': grund,
                                               'versuche': self.versuche.get(self.ziel['id'], 1),
                                               'zeit': time.strftime('%Y-%m-%d %H:%M:%S')}
        self._speichern()
        self.ziel = self.ziel_seit = None
        self.ankunft_bestaetigt = False

    def _speichern(self):
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            self.datei.write_text(json.dumps(self.erledigt, ensure_ascii=False, indent=1), encoding='utf-8')
        except OSError:
            pass
