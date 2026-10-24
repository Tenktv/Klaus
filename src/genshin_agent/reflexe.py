"""Schnelle Pixel-Reflexe für den Autopiloten: Bild rein, Tastenbefehle raus.

Keine Fenster- oder Eingabezugriffe hier. Die App führt die Befehle aus und
prüft vorher Fokus und Rechte. Positionen sind relativ zur Bildhöhe und an
echten 1080p-Spielbildern vom 18.10.2026 vermessen.

Navigation: Die Minimap ist genordet („N“ immer oben). Der helle Sichtkegel
zeigt die Kamerarichtung, das goldene Symbol die Questrichtung. Lenken heißt:
Kamera um die Differenz drehen. Wie viele Mauszähler ein Grad sind, lernt der
Pilot bei jeder Drehung am Kegel nach. Winkel: 0° = Norden/oben, im Uhrzeigersinn.
"""
from collections import deque
import math
from pathlib import Path
import time

import numpy as np

# Bereiche, in denen rote Pixel zur Oberfläche oder zur eigenen Figur gehören.
HUD = [(0.0, 0.0, 0.26, 0.42), (0.84, 0.0, 1.0, 0.75), (0.0, 0.84, 1.0, 1.0),
       (0.88, 0.0, 1.0, 0.12), (0.40, 0.35, 0.60, 0.95)]

FARBEN = {
    # Farbton in Grad, Mindestsättigung, Mindesthelligkeit. Gold sehr satt und hell: Wüstensand auf
    # der Minimap (Sumeru) ist ebenfalls goldgelb (Sättigung ~0,5) und verzog sonst die Richtung.
    'gold': (30, 60, 0.7, 200),      # Archon-/Hauptquest
    'lila': (265, 295, 0.35, 160),   # Storyquest
    'blau': (195, 215, 0.45, 190),   # Weltquest
}

# Minimap-Mitte (Spielerpfeil) und Radius, in Einheiten der Bildhöhe.
KARTE_X, KARTE_Y, KARTE_R = 0.1542, 0.1139, 0.087
# „N“ über der Minimap: Mitte und Graustufen-Muster (0-9) aus einem echten 1080p-Bild.
N_X, N_Y = 0.1556, 0.0343
N_MUSTER = [
    '000000000000000000000',
    '001111100000011111000',
    '006999960000179997200',
    '000489982000007950000',
    '000089998200004920000',
    '000089999810003910000',
    '000087799970003920000',
    '000085189995003920000',
    '000085028999303920000',
    '000086004899923920000',
    '000086000599984920000',
    '000086000079999920000',
    '000086000007999920000',
    '000086000002899920000',
    '000087000000399920000',
    '000288100000048920000',
    '004889820000006920000',
    '003333330000000300000',
    '000000000000000000000',
]
_N = np.array([[int(z) for z in zeile] for zeile in N_MUSTER], np.float32)
_N = (_N - _N.mean()) / _N.std()
HFOV = 73.0  # horizontales Sichtfeld der Spielkamera bei 16:9

# Goldene Quest-Raute in der Spielwelt (Domänen, Zielnähe): Goldmaske, gemittelt aus vier
# echten Bildern in 960x540. Rautenrahmen, gefüllter Kern, seitliche Flügel.
RAUTE_MUSTER = [
    '000000000000000000000000',
    '000000000000200000000000',
    '000000000004422000000000',
    '000000000279992000000000',
    '000000000299794000000000',
    '000000000292077000000000',
    '000000000400007700000000',
    '000000004207400700000000',
    '000020770027972072200000',
    '000047920779999207744000',
    '002799207799999920799200',
    '002992049999999740099700',
    '002992024999999740079700',
    '000299204799997700974000',
    '000022420449994004240000',
    '000000242047940040000000',
    '000000020004402200000000',
    '000000000420007000000000',
    '000000000272077000000000',
    '000000000099792000000000',
    '000000000079970000000000',
    '000000000002200000000000',
]
_RAUTE = np.array([[int(z) for z in zeile] for zeile in RAUTE_MUSTER], np.float32) / 9
_RAUTE = (_RAUTE - _RAUTE.mean()) / _RAUTE.std()
# Wo goldene Symbole zur Oberfläche gehören (Icons oben, Minimap, Questtext, Team, Leiste unten).
RAUTE_AUSSEN = [(0.0, 0.0, 1.0, 0.1), (0.0, 0.0, 0.16, 0.24), (0.0, 0.2, 0.06, 0.3),
                (0.84, 0.15, 1.0, 0.6), (0.84, 0.8, 1.0, 1.0), (0.0, 0.9, 1.0, 1.0)]
ELEMENTE = ('pyro', 'hydro', 'anemo', 'electro', 'cryo', 'geo', 'dendro')

# Interaktions-Hinweis rechts der Bildmitte („F  💬 Candace“, „F  Truhe öffnen“ …), Graustufen
# (0-9) aus einem echten Bild in 960x540: weiße Taste mit dunklem F, daneben das Symbol.
F_TASTE_MUSTER = [
    '000001101111000011000110',
    '001223233333222333332010',
    '018889999999888888888201',
    '148898998999989899988801',
    '168999999888888999889811',
    '168999996000103999998822',
    '169999999008887999999922',
    '169998999009999999999922',
    '169999999015658999999922',
    '169998999103227999999922',
    '169999989109999999999922',
    '169999999019999999999922',
    '259999999009999999999922',
    '169989998259999999999922',
    '069999999899999999999822',
    '169899989999999999999921',
    '148888888899899999999812',
    '127888888898999899998211',
    '101100210212222222222211',
    '110001001111222122212211',
]
# Sprechblase = Gespräch mit einer Figur (NPC); andere Symbole = Truhe, Gegenstand, Mechanismus.
BLASE_MUSTER = [
    '4201100111001100000000',
    '1111100000011001000000',
    '1101000123443110000000',
    '1011004899999974000000',
    '1100179999999999700000',
    '0101799999999999980010',
    '0004999999999999994000',
    '1019999999989999989100',
    '0008996799779976999100',
    '0119983399329933898000',
    '1008897899889988999100',
    '0018999999999999997000',
    '0112899999999999982000',
    '1000489899999999940001',
    '1110028998998898110000',
    '1000010168898888210110',
    '0100101111000389600000',
    '1010010001111011201001',
    '2001001110000010010010',
    '4210100000000001001001',
]
F_X = 0.5833          # Mitte der F-Taste, relativ zur Bildbreite
BLASE_ABSTAND = 0.0365  # Sprechblase so weit rechts der F-Taste


def _muster(zeilen):
    feld = np.array([[int(z) for z in zeile] for zeile in zeilen], np.float32)
    return (feld - feld.mean()) / feld.std()


_F_TASTE = _muster(F_TASTE_MUSTER)
_BLASE = _muster(BLASE_MUSTER)

# „▶ Auto“ links oben steht in jedem Dialog (weiß oder bei Antwortoptionen ausgegraut),
# unabhängig davon, wie hell die Szene ist. Graustufen aus einem echten Bild (960x540).
AUTO_MUSTER = [
    '1010100001100011000123332102222210000111000000000000000000000011',
    '0001101110011100001233221022222100000122100000000000000000000000',
    '0001001001135653212332101122221000001222210000000000111100111000',
    '0000001026787777774321111222210000012222220000000000111100000111',
    '0000101487778877787620121222110000022211122100000000100100000000',
    '0000015787887788788762212222100000122210122300000010000001000000',
    '0001037887889878888885222211000111232110113210101000000000000010',
    '0000177788856888887878432100011112772100112221000011001001010011',
    '0010387888842588878877721000011113994121011321013731010010011001',
    '0010777878832138898887820000011226797111111232005831010011001100',
    '0001878878841212788887830000022238489214881388249998306888411110',
    '1100788788831221258887740000133339168522991199225931169415941101',
    '0000778788842212228887750011232266139811991189336930298113870111',
    '0000787888832222388887831112322199999932991189336941298022972101',
    '0000787788842125888977821213211382227952990289236931199113951111',
    '0000587788832278888787712232101661113981797599325952249507830110',
    '0001277878842878878778522222011741112392167327123887113897200111',
    '0122368878888888787877222211111101110210111011012222332001001101',
    '0133446787788877877773212101011111101011010001112222221100100101',
    '1233322777887788787743221011100010110100101100011222323000001100',
    '2233210267778887776423211111111000000000000000111112232100011101',
    '2321112223678778633222111011111100000000000000011111222100001000',
    '2221122222210000112232111111111100000000000000011111122210000000',
    '2101122221000000123321000011110000000000000000111110123220000000',
    '2101222210000001222210011111100000000000000000011111122221000000',
]
_AUTO = _muster(AUTO_MUSTER)

# Schließen-X oben rechts: haben Menüs (Karte, Questbuch, Domänen-Eingang), Zwischensequenzen nicht.
X_MUSTER = [
    '1011111111111101100011111111111101',
    '1110110001111101110011111110111111',
    '0000000000111100110111111110111111',
    '0000100100011110011001111111011110',
    '0000001110101355444554211111001110',
    '1111011100245555544454453111010110',
    '0111111113555555555555445521111010',
    '1000001145555799989998644453101011',
    '0001000454579989888888995444310011',
    '0111104445899898889889999744430011',
    '1111124459989988888999999974441101',
    '1111154479733457899965433895443001',
    '1011355599822229988982322998455010',
    '1111555889822227999952133989655300',
    '1111545989923112889612124998955510',
    '0112556999848211286221375988955520',
    '1113548988899931121225989988965521',
    '1114459888899993211259888888965521',
    '1114449888888996211299888888965521',
    '1004458888899961112229988988864421',
    '0102557989989611153212898888954511',
    '0001456899933121599322234888854411',
    '0000445989822124999921233988845401',
    '0000344799822239989992222989555202',
    '0000044498722227889962222997555101',
    '1111144459877898888888877995553110',
    '1111015445989999888888989855541110',
    '0000002445588999888888888554421111',
    '0000100244457998888988965444201111',
    '0100100024544567888876544441111111',
    '1011010000454455455444444311111111',
    '1010000110014554544555531111111111',
    '0000110100011123445431234321441111',
    '1110110100010101111114411241331111',
]
_X = _muster(X_MUSTER)


def menue_x(klein):
    """Schließen-X oben rechts (Menü, Karte, Questbuch) – nur dann ist ESC sinnvoll."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    feld = klein[:int(60 * k), max(0, int(breite - 80 * k)):].astype(np.float32).min(axis=2)
    return _beste_ncc(feld, _skaliert(_X, hoehe))[0] > 0.6


def _glatt(feld):
    """3x3-Mittelwert: Schriftvergleiche werden unempfindlich gegen die Pixel-Halbierung."""
    rand = np.pad(feld, 1, mode='edge')
    return sum(rand[dy:dy + feld.shape[0], dx:dx + feld.shape[1]] for dy in range(3) for dx in range(3)) / 9


def _vorlage_datei(name, glatt=False):
    """Größere Vorlagen liegen als Graustufenbild (960x540-Maßstab) in vorlagen/."""
    from PIL import Image
    feld = np.asarray(Image.open(Path(__file__).resolve().parent / 'vorlagen' / name).convert('L')).astype(np.float32)
    if glatt:
        feld = _glatt(feld)
    return (feld - feld.mean()) / feld.std()


# Weltkarte: freigeschalteter Teleportpunkt = weißer Pin mit hellblauer Raute (gesperrt: grau);
# Teleport-Knopf unten rechts im Teleportpunkt-Fenster (mit F auslösbar). Aus echten Bildern.
_PIN = _vorlage_datei('teleportpunkt.png')
_PIN_RAUTE = (9, 8)  # Lage der Raute in der Pin-Vorlage (Zeile, Spalte)
_STATUE = _vorlage_datei('statue.png')
_STATUE_MITTE = (12, 10)  # blauer Kreis; die Statue ist ebenfalls ein Teleportziel
_KARTE_PLUS = _vorlage_datei('karte_zoom_plus.png')
_TELEPORT_KNOPF = _vorlage_datei('teleport_knopf.png')
# Beim Klettern zeigt Genshin unten rechts „Absteigen [X]“ statt der Fähigkeiten R/E/Q.
_KLETTERN = _vorlage_datei('klettern.png')
_GLEITEN = _vorlage_datei('gleiten.png')
_E_TASTE = _vorlage_datei('e_taste.png')
# Auge- und Lautsprecher-Symbol neben „Auto“: bleiben weiß, auch wenn „Auto“ bei Antwortoptionen
# ausgegraut und auf hellem Himmel unsichtbar ist (Cyno-Dialog in der Wüste).
_DIALOG_SYMBOLE = _vorlage_datei('dialog_symbole.png')


_STOPPUHR = _vorlage_datei('stoppuhr.png')
# Truhen (Livebilder 23:01 und 21:56): weißes Truhensymbol im Rautenrahmen über der Truhe, mit
# Entfernung darunter oder am Bildrand mit Pfeil; im F-Hinweis das kleine Truhensymbol.
_TRUHE_MARKER = _vorlage_datei('truhe_marker.png')
_TRUHE_F = _vorlage_datei('truhe_f.png')


def truhe(klein):
    """Truhen-Symbol in der Welt (erscheint z. B. nach „Defeat all opponents“): (x, y, güte) oder
    None. Truhensymbole 0,89-1,00, sonst höchstens 0,77 (Sprechblase, Questsymbole)."""
    hoehe, breite = klein.shape[:2]
    vorlage = _skaliert(_TRUHE_MARKER, hoehe)
    th, tb = vorlage.shape
    ncc = _ncc_feld(klein.astype(np.float32).min(axis=2), vorlage)
    # Oberfläche: Minimap/Questtext, Teamleiste, Leiste unten, Symbole oben rechts.
    for x0, y0, x1, y1 in ((0, 0, .27, .42), (.84, 0, 1, .75), (0, .84, 1, 1), (.6, 0, 1, .12)):
        ncc[max(0, int(y0 * hoehe) - th):int(y1 * hoehe), max(0, int(x0 * breite) - tb):int(x1 * breite)] = -1
    y, x = np.unravel_index(int(ncc.argmax()), ncc.shape)
    if ncc[y, x] < .85:
        return None
    return (x + tb / 2) / breite, (y + th / 2) / hoehe, float(ncc[y, x])


def herausforderung(klein):
    """Kampf-Herausforderung läuft: Stoppuhr oben in der Mitte („Opponents Defeated 1/9“)."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    feld = klein[int(8 * k):int(60 * k), int(breite / 2 - 80 * k):int(breite / 2 + 40 * k)]
    return _beste_ncc(feld.astype(np.float32).min(axis=2), _skaliert(_STOPPUHR, hoehe))[0] > 0.75


# Kampfziel im Questtracker: „Defeat …“ am Zeilenanfang unter der Minimap (Livebilder 21:54,
# 21:56, 22:10 „Defeat all opponents x/6“; Hauptquest „Defeat the attacking Fatui“ unterstrichen).
_KAMPFZIEL = _vorlage_datei('kampfziel.png', glatt=True)


def kampfziel(klein):
    """Der Questtracker verlangt einen Kampf („Defeat all opponents 0/6“). Solange das dasteht,
    sind noch Gegner übrig – auch wenn gerade keiner im Bild ist. Geglättet verglichen:
    Kampfziele 0,83–0,99, andere Questtexte („Go to …“) höchstens 0,65."""
    hoehe = klein.shape[0]
    k = hoehe / 540
    vorlage = _skaliert(_KAMPFZIEL, hoehe)
    x0 = int(28 * k)
    feld = klein[int(.17 * hoehe):int(.45 * hoehe), x0:x0 + vorlage.shape[1] + int(16 * k)]
    return _beste_ncc(_glatt(feld.astype(np.float32).min(axis=2)), vorlage)[0] > 0.75


# Fähigkeiten und Teamleiste, in 1080p-Pixeln vermessen (x vom rechten Bildrand aus).
Q_KNOPF = (100, 972, 46)               # Q-Knopf unten rechts: Mitte und Radius
TEAM_Y = (275, 365, 458, 548)          # Zeilen der vier Teamplätze
TEAM_Q_X, TEAM_Q_R = 303, 20           # Explosionssymbol links neben dem Namen
TEAM_NR = (59, 37)                     # Nummernfeld rechts (von/bis)


_KREISE = {}


def _kreis_kontrast(klein, x_rechts, y, radius):
    """Streuung des Minimalkanals in einem Kreis: deckende, leuchtende Symbole sind kontrastreich,
    durchscheinende (nicht bereit) zeigen nur die Spielwelt dahinter."""
    hoehe, breite = klein.shape[:2]
    schluessel = (hoehe, breite, x_rechts, y, radius)
    if schluessel not in _KREISE:
        k = hoehe / 1080
        cx, cy, r = breite - x_rechts * k, y * k, radius * k
        y0, x0 = max(0, int(cy - r)), max(0, int(cx - r))
        y1, x1 = min(hoehe, int(cy + r) + 2), min(breite, int(cx + r) + 2)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        _KREISE[schluessel] = (slice(y0, y1), slice(x0, x1), np.hypot(xx - cx, yy - cy) < r)
    zeilen, spalten, maske = _KREISE[schluessel]
    innen = klein[zeilen, spalten].min(axis=2)[maske]
    return float(innen.std()) if innen.size else 0.0


def q_bereit(klein):
    """Elementarexplosion der aktiven Figur bereit: Der Q-Knopf ist dann ein deckendes, leuchtendes
    Symbol (Kontrast 64–84 bei Venti, Hu Tao, Qiqi, Vodyanitsa). Ladend ist er durchscheinend,
    in der Abklingzeit zeigt er nur Sekunden (höchstens 54)."""
    return _kreis_kontrast(klein, *Q_KNOPF) >= 60


def team_status(klein):
    """(aktiver Platz 1-4 oder None, Plätze mit bereitem Q). Das Nummernfeld der aktiven Figur
    ist grau statt weiß; bei anderen Figuren mit voller Energie leuchtet links neben dem Namen
    ihr Explosionssymbol (Kontrast 70–82, Hintergrund höchstens ~61)."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 1080
    hell = []
    for y in TEAM_Y:
        box = klein[int((y - 11) * k):int((y + 11) * k), int(breite - TEAM_NR[0] * k):int(breite - TEAM_NR[1] * k)]
        hell.append(float(np.percentile(box.min(axis=2), 90)) if box.size else 0.0)
    weiss = [h >= 245 for h in hell]
    aktiv = None
    if sum(weiss) == len(TEAM_Y) - 1 and hell[weiss.index(False)] < 225:
        aktiv = weiss.index(False) + 1
    # Nur Plätze mit weißem Nummernfeld: Teamleiste sichtbar und nicht die aktive Figur
    # (deren Name rückt nach links und läge sonst im Symbolbereich).
    bereit = tuple(i + 1 for i, y in enumerate(TEAM_Y) if weiss[i] and _kreis_kontrast(klein, TEAM_Q_X, y, TEAM_Q_R) >= 66)
    return aktiv, bereit


# Gegnerpfeile liegen auf einer Ellipse um die Bildmitte: Halbachsen 26,6 % der Breite und
# 37 % der Höhe (sechs Livebilder 22:10 und die älteren Testbilder: Radius 0,96–1,07).
PFEIL_A, PFEIL_B = 0.266, 0.37


def pfeil_winkel(x, y):
    """Richtung eines Gegnerpfeils relativ zur Blickrichtung: 0 vorn, +90 rechts, ±180 hinten."""
    return math.degrees(math.atan2((x - .5) / PFEIL_A, -(y - .5) / PFEIL_B))


def _pfeil_ring(hoehe, breite):
    ringe = getattr(_pfeil_ring, '_cache', {})
    if (hoehe, breite) not in ringe:
        yy, xx = np.mgrid[:hoehe, :breite]
        rho = np.hypot((xx / breite - .5) / PFEIL_A, (yy / hoehe - .5) / PFEIL_B)
        # Unten endet der Ring über dem eigenen HP-Balken (y 0,92).
        ringe[(hoehe, breite)] = (rho > .82) & (rho < 1.18) & (yy < .91 * hoehe)
        _pfeil_ring._cache = ringe
    return ringe[(hoehe, breite)]


def gegner_pfeile(klein):
    """Rot-rosa Pfeile, mit denen Genshin Gegner außerhalb des Bildes anzeigt: [(x, y)] relativ.
    Gesucht wird nur im Ring um die Pfeil-Ellipse – dort liegen weder Minimap, Questtext und
    Teamleiste noch die Figur mit Begleiter-Blase. Früher war die Bildmitte ganz gesperrt; genau
    dort (unter der Figur) zeigen die Pfeile aber Gegner hinter ihm (Livebild 22:10:34).
    Farbe/Größe filtern Kandidaten, die gedrehte Pfeilkontur bestätigt sie."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    rgb = klein.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Rosa (Blau über Grün) oder korallrot (255/100/95 auf Gras: Blau ≈ Grün).
    # Feuer und Glut haben deutlich mehr Grün als Blau.
    maske = (r > 190) & (r - g > 80) & (r - b > 40) & (b > g - 20) & _pfeil_ring(hoehe, breite)
    if maske.sum() < 25 * k * k:
        return []
    # Zusammenhängende Flecken über ein grobes Raster (6x6-Zellen) finden.
    zelle = max(3, round(6 * k))
    zh, zb = hoehe // zelle, breite // zelle
    zellen = maske[:zh * zelle, :zb * zelle].reshape(zh, zelle, zb, zelle).sum(axis=(1, 3)) > 0
    besucht = np.zeros_like(zellen)
    pfeile = []
    for start in zip(*np.nonzero(zellen)):
        if besucht[start]:
            continue
        stapel, gruppe = [start], []
        besucht[start] = True
        while stapel:
            zy, zx = stapel.pop()
            gruppe.append((zy, zx))
            for ny, nx in ((zy + 1, zx), (zy - 1, zx), (zy, zx + 1), (zy, zx - 1)):
                if 0 <= ny < zh and 0 <= nx < zb and zellen[ny, nx] and not besucht[ny, nx]:
                    besucht[ny, nx] = True
                    stapel.append((ny, nx))
        ys = [p[0] for p in gruppe]
        xs = [p[1] for p in gruppe]
        y0, y1, x0, x1 = min(ys) * zelle, (max(ys) + 1) * zelle, min(xs) * zelle, (max(xs) + 1) * zelle
        punkte = int(maske[y0:y1, x0:x1].sum())
        if not 30 * k * k <= punkte <= 300 * k * k:
            continue
        # Dichte auf der engen Box: das grobe Raster blähte dünne Kerbenpfeile auf (0,23 statt 0,37).
        py, px = np.nonzero(maske[y0:y1, x0:x1])
        h, w = py.max() - py.min() + 1, px.max() - px.min() + 1
        if 0.5 <= w / h <= 2.2 and punkte / (w * h) > 0.3:
            # Ein grobes Raster kann einen rosa Begleiter in kompakte Flecken teilen.
            # Deshalb echte Pfeilform aus Kampfaufnahmen prüfen, in allen Richtungen: gefüllt
            # (Wüste) und mit Kerbe – äußerer Winkel plus kleines Dreieck (Gras, Livebild 22:10:31).
            # Nur Kandidaten durchsuchen und die kleinen Vorlagen je Auflösung behalten.
            konturen = getattr(gegner_pfeile, '_konturen', {})
            if hoehe not in konturen:
                from PIL import Image
                konturen[hoehe] = []
                for datei in ('gegner_pfeil.png', 'gegner_pfeil_kerbe.png', 'gegner_pfeil_hinten.png'):
                    with Image.open(Path(__file__).resolve().parent / 'vorlagen' / datei) as vorlage:
                        vorlage = vorlage.convert('L')
                        for grad in range(0, 360, 10):
                            feld = np.asarray(vorlage.rotate(grad, Image.Resampling.BILINEAR)).astype(np.float32)
                            feld = (feld - feld.mean()) / feld.std()
                            konturen[hoehe].append(_skaliert(feld, hoehe))
                konturen[hoehe] = np.stack(konturen[hoehe])
                gegner_pfeile._konturen = konturen
            rand = max(4, round(8 * k))
            feld = maske[max(0, y0 - rand):min(hoehe, y1 + rand),
                         max(0, x0 - rand):min(breite, x1 + rand)].astype(np.float32) * 255
            vorlagen = konturen[hoehe]
            th, tb = vorlagen.shape[1:]
            if feld.shape[0] < th or feld.shape[1] < tb:
                continue
            # Alle Drehungen gemeinsam vergleichen: Fensterstatistik nur einmal berechnen.
            fenster = np.lib.stride_tricks.sliding_window_view(feld, (th, tb)).reshape(-1, th * tb)
            abw = fenster.std(axis=1)
            werte = fenster @ vorlagen.reshape(len(vorlagen), -1).T
            werte /= th * tb * np.maximum(abw[:, None], 1e-3)
            if not np.any((werte >= 0.80) & (abw[:, None] >= 8)):
                continue
            pfeile.append(((x0 + x1) / 2 / breite, (y0 + y1) / 2 / hoehe))
    return pfeile


def dialog_symbole(klein):
    hoehe = klein.shape[0]
    k = hoehe / 540
    feld = klein[:int(52 * k), int(110 * k):int(216 * k)].astype(np.float32).min(axis=2)
    return _beste_ncc(feld, _skaliert(_DIALOG_SYMBOLE, hoehe))[0] > 0.6


def dialog_option(klein):
    """F-Taste neben einer Antwortoption („F 💬 Yes, I remember.“) bei x≈0,64: y relativ oder None."""
    treffer = _f_taste(klein, (0.60, 0.68), (0.30, 0.88))
    return None if treffer is None else treffer[2]


def klettert(klein):
    """Figur hängt an einer Wand (Kletter-Anzeige unten rechts)."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    feld = klein[int(464 * k):int(540 * k), max(0, int(breite - 190 * k)):int(breite - 120 * k)]
    return _beste_ncc(feld.astype(np.float32).min(axis=2), _skaliert(_KLETTERN, hoehe))[0] > 0.8


def gleitet(klein):
    """Geöffneter Gleiter: weißes Absteigen/Leertaste-Symbol im Fähigkeitenbereich.

    Das Symbol ersetzt beim Gleiten die Elementarfähigkeit; es ist unabhängig
    von den sichtbaren Flügeln der jeweiligen Figur und Kameraperspektive.
    """
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    feld = klein[int(467*k):int(520*k), max(0, int(breite-140*k)):int(breite-70*k)]
    return _beste_ncc(feld.astype(np.float32).min(axis=2), _skaliert(_GLEITEN, hoehe))[0] > .82


def faehigkeitstaste_sichtbar(klein):
    """E-Tastenfeld statt der breiten Leertaste: zusätzliche Bestätigung Gleiter zu."""
    hoehe, breite = klein.shape[:2]
    k = hoehe/540
    feld = klein[int(506*k):int(536*k), max(0, int(breite-137*k)):int(breite-70*k)]
    return _beste_ncc(feld.astype(np.float32).min(axis=2), _skaliert(_E_TASTE, hoehe))[0] > .88


def _ncc_feld(grau, vorlage):
    """Normierte Kreuzkorrelation über das ganze Bild per FFT (Index = linke obere Ecke)."""
    th, tb = vorlage.shape
    n = th * tb
    form = (-(-(grau.shape[0] + th) // 64) * 64, -(-(grau.shape[1] + tb) // 64) * 64)
    zaehler = np.fft.irfft2(np.fft.rfft2(grau, form) * np.conj(np.fft.rfft2(vorlage, form)), form)
    zaehler = zaehler[:grau.shape[0] - th + 1, :grau.shape[1] - tb + 1]
    summe = np.pad(grau.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    quadrat = np.pad((grau ** 2).cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def fenster(feld):
        return feld[th:, tb:] - feld[:-th, tb:] - feld[th:, :-tb] + feld[:-th, :-tb]
    mittel = fenster(summe) / n
    abw = np.sqrt(np.maximum(fenster(quadrat) / n - mittel ** 2, 0))
    ncc = zaehler / (n * np.maximum(abw, 1e-3))
    ncc[abw < 10] = -1
    return ncc


def teleportpunkte(klein):
    """Teleportpunkte auf der Weltkarte: [{'x','y','offen','abstand'}], x/y relativ, nach Abstand zur
    Bildmitte sortiert (nach „Navigieren“ steht dort das Questziel). offen = freigeschaltet."""
    hoehe, breite = klein.shape[:2]
    vorlage = _skaliert(_PIN, hoehe)
    k = hoehe / 540
    ncc = _ncc_feld(klein.astype(np.float32).min(axis=2), vorlage)
    rgb = klein.astype(np.int16)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Raute im Pin: frei = blau/türkis, gesperrt = dunkelgrau. Gezählt im ganzen Pinkopf statt an
    # einem festen Punkt – bei anderer Zoomstufe sitzt die Raute woanders (Inazuma-Karte 23:00:
    # freie Pins galten als grau). Frei 18-31 Pixel, gesperrt 0, Küste/Questsymbol dazwischen.
    blau = (b_ > 120) & (b_ - r_ > 60) & (b_ >= g_ - 10)
    gold = (r_ > 180) & (g_ > 120) & (b_ < 90)
    punkte = []
    for _ in range(60):
        y, x = np.unravel_index(int(ncc.argmax()), ncc.shape)
        if ncc[y, x] < 0.6:
            break
        my, mx = int(y + _PIN_RAUTE[0] * k), int(x + _PIN_RAUTE[1] * k)
        box = (slice(max(0, my - round(9 * k)), my + round(4 * k)), slice(max(0, mx - round(6 * k)), mx + round(7 * k)))
        anzahl, verdeckt = int(blau[box].sum()) / (k * k), int(gold[box].sum()) / (k * k)
        offen = anzahl >= 15
        sicher = offen or (anzahl <= 3 and verdeckt <= 10)
        px, py = mx / breite, my / hoehe
        punkte.append({'x': px, 'y': py, 'offen': offen, 'sicher': sicher,
                       'abstand': math.hypot((px - 0.5) * breite / hoehe, py - 0.5)})
        ncc[max(0, y - int(10 * k)):y + int(10 * k), max(0, x - int(10 * k)):x + int(10 * k)] = -1
    return sorted(punkte, key=lambda p: p['abstand'])


def karte_offen(klein):
    """Weltkarte: Pins oder Schließen-X zusammen mit dem eigenen Zoomregler.

    Bei großem Kartenabstand können Teleportpins verschwinden. Menüs haben
    ebenfalls ein X, deshalb muss in diesem Fall zusätzlich der Regler passen:
    Karten 0,60-1,00, andere Menüs mit X höchstens 0,17. Die frühere Schwelle 0,75
    lehnte herausgezoomte Karten ab – die Suche brach nach dem Zoomen ab (Livelauf 23:00).
    """
    if len(teleportpunkte(klein)) >= 3:
        return True
    if not menue_x(klein):
        return False
    k = klein.shape[0] / 540
    feld = klein[int(200*k):int(244*k), int(5*k):int(43*k)].astype(np.float32).min(axis=2)
    return _beste_ncc(feld, _skaliert(_KARTE_PLUS, klein.shape[0]))[0] > .5


def teleportziele(klein):
    """Wegpunkte und Statuen der Sieben auf einer zuvor bestätigten Weltkarte.

    Gesperrte graue Symbole bleiben zur Diagnose enthalten. Nur blaue Symbole
    werden als freigeschaltet gewertet; vor F wird immer der Teleportknopf geprüft.
    """
    punkte = [dict(p, art='wegpunkt') for p in teleportpunkte(klein)]
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    vorlage = _skaliert(_STATUE, hoehe)
    ncc = _ncc_feld(klein.astype(np.float32).min(axis=2), vorlage)
    rgb = klein.astype(np.int16)
    blau = (rgb[..., 2] > 170) & (rgb[..., 2] - rgb[..., 0] > 75) & (rgb[..., 1] > 110)
    for _ in range(30):
        y, x = np.unravel_index(int(ncc.argmax()), ncc.shape)
        if ncc[y, x] < .7:
            break
        my, mx = round(y + _STATUE_MITTE[0] * k), round(x + _STATUE_MITTE[1] * k)
        r = max(3, round(5 * k))
        anzahl = int(blau[max(0, my-r):my+r+1, max(0, mx-r):mx+r+1].sum())
        offen = anzahl >= 12 * k * k
        px, py = mx / breite, my / hoehe
        if py > .07 and py < .92 and not (px < .19 and py < .3):
            punkte.append({'x': px, 'y': py, 'offen': offen, 'sicher': offen or anzahl <= 2 * k * k, 'art': 'statue',
                           'abstand': math.hypot((px-.5)*breite/hoehe, py-.5)})
        ry, rx = max(1, round(20*k)), max(1, round(15*k))
        ncc[max(0,y-ry):y+ry+1, max(0,x-rx):x+rx+1] = -1
    return sorted(punkte, key=lambda p: p['abstand'])


def teleport_knopf(klein):
    """„Teleport“-Knopf unten rechts im Teleportpunkt-Fenster (nicht „Cancel Navigation“)."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    vorlage = _skaliert(_TELEPORT_KNOPF, hoehe)
    # Fenster hängt am rechten Rand: Knopf bei x 720-880, y 488-518 (960x540), ±12 px suchen.
    x0 = max(0, int(breite - (960 - 708) * k))
    feld = klein[int(476 * k):int(530 * k), x0:int(breite - (960 - 892) * k)].astype(np.float32).min(axis=2)
    return _beste_ncc(feld, vorlage)[0] > 0.7


def dialog_auto(klein):
    """Ähnlichkeit mit dem „▶ Auto“-Knopf links oben (Dialoge: 0,82-0,99; sonst unter 0,5)."""
    hoehe = klein.shape[0]
    k = hoehe / 540
    grau = klein[int(4 * k):int(46 * k), int(10 * k):int(100 * k)].astype(np.float32).min(axis=2)
    return _beste_ncc(grau, _skaliert(_AUTO, hoehe))[0]


def spur(klein):
    """Goldene Glitzerspur der Questnavigation (Taste V) am Boden: (x, y) ihres nächsten Abschnitts
    relativ, oder None. Nur kleine einzelne Funken zählen – Lampen sind große helle Flecken."""
    hoehe, breite = klein.shape[:2]
    rgb = klein.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Helle gelbweiße Funken. Die Ausdauer-Anzeige (~240/190/20-110) fällt schon durch Grün < 215.
    funke = (r > 235) & (g > 215) & (b > 80) & (b < 210) & (r - b > 40)
    funke[:int(0.3 * hoehe)] = False                      # Himmel, Icons, Minimap, Questtext
    funke[int(0.9 * hoehe):] = False                      # Leiste unten
    funke[:, int(0.84 * breite):] = False                 # Team
    # Eigene Figur samt Ausdauer-Bogen rechts daneben; die Spur zählt erst weiter weg.
    funke[int(0.2 * hoehe):, int(0.40 * breite):int(0.66 * breite)] = False
    if funke.sum() < 25:
        return None
    # Dichte im 9x9-Umfeld: Funken sind vereinzelt, Lampen und Glanzflächen dicht.
    f = funke.astype(np.float32)
    integral = np.pad(f.cumsum(0).cumsum(1), ((5, 4), (5, 4)), mode='edge')
    dichte = (integral[9:, 9:] - integral[:-9, 9:] - integral[9:, :-9] + integral[:-9, :-9]) / 81
    # Nur winzige Einzelpunkte (Glanz auf Stoff/Metall ist flächig) …
    ys, xs = np.nonzero(funke & (dichte[:hoehe, :breite] < 0.15))
    if len(xs) < 12:
        return None
    # Nur eine räumlich zusammenhängende Funkenkette verfolgen. Einzelner
    # Sonnenglanz nahe den Füßen darf nicht das nahe Ende der echten Spur ersetzen.
    zelle = max(4, round(8*hoehe/540))
    gruppen = {}
    for i, (x, y) in enumerate(zip(xs.tolist(), ys.tolist())):
        gruppen.setdefault((x//zelle, y//zelle), []).append(i)
    if len(gruppen) > 500:
        return None  # großflächiges Glitzern darf die schnelle Rettungsschleife nicht blockieren
    rest, ketten = set(gruppen), []
    radius = .13*hoehe/zelle
    reichweite = math.ceil(radius)
    while rest:
        start = rest.pop()
        stapel, gruppe, zellen = [start], [], 0
        while stapel:
            x, y = stapel.pop()
            gruppe.extend(gruppen[(x, y)])
            zellen += 1
            for dx in range(-reichweite, reichweite+1):
                for dy in range(-reichweite, reichweite+1):
                    if dx*dx+dy*dy > radius*radius:
                        continue
                    nachbar = (x+dx, y+dy)
                    if nachbar in rest:
                        rest.remove(nachbar)
                        stapel.append(nachbar)
        xx, yy = xs[gruppe], ys[gruppe]
        if zellen >= 5 and math.hypot(np.ptp(xx), np.ptp(yy)) >= .12*hoehe:
            ketten.append((np.ptp(yy)+.25*np.ptp(xx), gruppe))
    if not ketten:
        return None
    _, gruppe = max(ketten, key=lambda k: k[0])
    xs, ys = xs[gruppe], ys[gruppe]
    # Lokales Vorschauziel statt fernstem Funken: eine Spur kann erst um einen
    # Pfeiler herum und dahinter wieder zurück führen. Ihre Kurve nicht abkürzen.
    nah = ys >= ys.max() - (ys.max()-ys.min())*.35
    return float(np.median(xs[nah]))/breite, float(np.median(ys[nah]))/hoehe


def verkleinern(bild, breite=960):
    """RGB-Array grob verkleinern (Schrittweite), schnell genug für 10 Hz."""
    schritt = max(1, bild.shape[1] // breite)
    return np.ascontiguousarray(bild[::schritt, ::schritt, :3])


def _hsv(bild):
    rgb = bild.astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    d = np.maximum(mx - mn, 1e-3)
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    s = (mx - mn) / np.maximum(mx, 1e-3)
    return h, s, mx


def _hud_maske(hoehe, breite):
    maske = np.ones((hoehe, breite), bool)
    for x0, y0, x1, y1 in HUD:
        maske[int(y0*hoehe):int(y1*hoehe), int(x0*breite):int(x1*breite)] = False
    return maske


def _groesster_fleck(maske, mindestens):
    """Schwerpunkt der dichtesten Rasterzelle (+Nachbarn) als (x, y, pixel) relativ."""
    hoehe, breite = maske.shape
    zh, zb = 18, 32
    zellen = maske[:hoehe//zh*zh, :breite//zb*zb].reshape(zh, hoehe//zh, zb, breite//zb).sum(axis=(1, 3))
    if zellen.max() < mindestens:
        return None
    zy, zx = np.unravel_index(int(zellen.argmax()), zellen.shape)
    y0, y1 = max(0, zy-1) * (hoehe//zh), min(zh, zy+2) * (hoehe//zh)
    x0, x1 = max(0, zx-1) * (breite//zb), min(zb, zx+2) * (breite//zb)
    ys, xs = np.nonzero(maske[y0:y1, x0:x1])
    return (float(xs.mean() + x0) / breite, float(ys.mean() + y0) / hoehe, int(len(xs)))


def winkel_diff(a, b):
    """Kleinster Winkel von b nach a in Grad (-180..180)."""
    return (a - b + 180) % 360 - 180


def bildwinkel(x):
    """Horizontale Bildposition (0..1) als Winkel zur Blickrichtung in Grad."""
    return math.degrees(math.atan((x - 0.5) * 2 * math.tan(math.radians(HFOV / 2))))


def _auf_1080(ausschnitt, hoehe):
    """Bildausschnitt auf 1080p-Maßstab bringen, damit feste Muster passen."""
    if abs(hoehe - 1080) < 2:
        return ausschnitt
    from PIL import Image
    faktor = 1080 / hoehe
    groesse = (max(1, round(ausschnitt.shape[1] * faktor)), max(1, round(ausschnitt.shape[0] * faktor)))
    return np.asarray(Image.fromarray(np.ascontiguousarray(ausschnitt)).resize(groesse))


def n_wert(bild):
    """Ähnlichkeit (-1..1) mit dem „N“ über der Minimap; hoch = Karte sichtbar."""
    hoehe = bild.shape[0]
    mh, mb = _N.shape
    suche = 4
    halb_h, halb_b = (mh // 2 + suche) * hoehe / 1080, (mb // 2 + suche) * hoehe / 1080
    x, y = N_X * hoehe, N_Y * hoehe
    feld = bild[max(0, int(y - halb_h)):int(y + halb_h) + 1, max(0, int(x - halb_b)):int(x + halb_b) + 1, :3]
    feld = _auf_1080(feld, hoehe).astype(np.float32).min(axis=2)
    beste = -1.0
    for dy in range(0, feld.shape[0] - mh + 1):
        for dx in range(0, feld.shape[1] - mb + 1):
            stueck = feld[dy:dy + mh, dx:dx + mb]
            abw = stueck.std()
            if abw > 1:
                beste = max(beste, float(((stueck - stueck.mean()) / abw * _N).mean()))
    return beste


def hp_balken(klein):
    """Grüner eigener Lebensbalken unten in der Mitte (nur im normalen Spiel sichtbar)."""
    hoehe, breite = klein.shape[:2]
    band = klein[int(hoehe*0.92):int(hoehe*0.95), int(breite*0.42):int(breite*0.47)].astype(np.int16)
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    gruen = (g > 140) & (g > r + 30) & (g > b + 60)
    return bool(gruen.size) and float(gruen.mean(axis=1).max()) > 0.25


def eigene_hp(klein):
    """Grobe Füllung des eigenen HP-Balkens (grün/gelb/rot), sonst None.

    Weiße Zahlen werden nicht mitgezählt. Keine Lebenspunkte aus der Teamleiste.
    """
    h, w = klein.shape[:2]
    band = klein[int(.923*h):int(.944*h), int(.42*w):int(.585*w)].astype(np.int16)
    if not band.size:
        return None
    r, g, b = band.transpose(2, 0, 1)
    farbe = (((g > 140) & (g-r > 25) & (g-b > 55))
             | ((r > 170) & (g > 140) & (b < 120))
             | ((r > 170) & (g < 125) & (b < 125) & (r-g > 70)))
    spalten = np.flatnonzero(farbe.sum(axis=0) >= max(1, round(2*h/540)))
    if len(spalten) < 3 or spalten[0] > .012*w:
        return None
    return float(np.clip((spalten[-1]+1)/(.16*w), 0, 1))


def hud_sichtbar(voll, klein):
    """Normales, steuerbares Spiel: Minimap-N oder eigener HP-Balken sichtbar."""
    return hp_balken(klein) or n_wert(voll) > 0.55


def _beste_ncc(feld, vorlage):
    """Normierte Kreuzkorrelation über alle Positionen (vektorisiert): (wert, y, x)."""
    mh, mb = vorlage.shape
    if feld.shape[0] < mh or feld.shape[1] < mb:
        return -1.0, 0, 0
    fenster = np.lib.stride_tricks.sliding_window_view(feld, (mh, mb))
    mittel = fenster.mean(axis=(2, 3), keepdims=True)
    abw = fenster.std(axis=(2, 3))
    werte = ((fenster - mittel) * vorlage).mean(axis=(2, 3)) / np.maximum(abw, 1e-3)
    werte[abw < 8] = -1  # einfarbige Flächen sind keine Symbole
    y, x = np.unravel_index(int(werte.argmax()), werte.shape)
    return float(werte[y, x]), int(y), int(x)


def _skaliert(vorlage, hoehe):
    if abs(hoehe - 540) <= 2:
        return vorlage
    from PIL import Image
    faktor = hoehe / 540
    groesse = (max(6, round(vorlage.shape[1] * faktor)), max(6, round(vorlage.shape[0] * faktor)))
    feld = np.asarray(Image.fromarray(vorlage).resize(groesse))
    return (feld - feld.mean()) / feld.std()


def _f_taste(klein, x_bereich, y_bereich):
    """Weiße F-Taste im Bereich suchen: (güte, mitte_x, mitte_y) relativ oder None."""
    hoehe, breite = klein.shape[:2]
    taste = _skaliert(_F_TASTE, hoehe)
    th, tb = taste.shape
    x0, y0 = int(x_bereich[0] * breite), int(y_bereich[0] * hoehe)
    grau = klein[y0:int(y_bereich[1] * hoehe), x0:int(x_bereich[1] * breite)].astype(np.float32).min(axis=2)
    if grau.shape[0] < th or grau.shape[1] < tb:
        return None
    weiss = (grau > 200).astype(np.float32)
    integral = np.pad(weiss.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    anteil = (integral[th:, tb:] - integral[:-th, tb:] - integral[th:, :-tb] + integral[:-th, :-tb]) / (th * tb)
    kandidaten = np.argwhere(anteil > 0.5)
    wert, y, x = -1.0, 0, 0
    for ky, kx in kandidaten[::max(1, len(kandidaten) // 40)]:
        stueck = grau[ky:ky + th, kx:kx + tb]
        abw = stueck.std()
        if abw > 8:
            ncc = float(((stueck - stueck.mean()) * taste).mean() / abw)
            if ncc > wert:
                wert, y, x = ncc, int(ky), int(kx)
    if wert < 0.6:
        return None
    return wert, (x0 + x + tb / 2) / breite, (y0 + y + th / 2) / hoehe


def f_hinweis(klein):
    """Sichtbarer Interaktions-Hinweis: {'y': relativ, 'gespraech': bool, 'truhe': bool} oder None.

    Gespräch nur bei eindeutiger Sprechblase: Das Truhensymbol („F ▸ Common Chest“) erreichte an
    der Blasen-Vorlage 0,55 und galt als Gespräch – er öffnete Truhen nie (Livebild 23:01:17).
    Echte Gespräche 1,00, Truhe 0,55, Gegenstände 0,22-0,48."""
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    taste = _skaliert(_F_TASTE, hoehe)
    th, tb = taste.shape
    x0 = max(0, int(F_X * breite - tb / 2 - 14 * k))
    y0 = int(0.36 * hoehe)
    grau = klein[y0:int(0.66 * hoehe), x0:x0 + tb + int(28 * k)].astype(np.float32).min(axis=2)
    # Vorfilter: Die Taste ist ein fast weißes Quadrat. Ohne so eine Stelle sofort fertig.
    weiss = (grau > 200).astype(np.float32)
    integral = np.pad(weiss.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    anteil = (integral[th:, tb:] - integral[:-th, tb:] - integral[th:, :-tb] + integral[:-th, :-tb]) / (th * tb)
    kandidaten = np.argwhere(anteil > 0.5)
    if not len(kandidaten):
        return None
    wert, y, x = -1.0, 0, 0
    for ky, kx in kandidaten[::max(1, len(kandidaten) // 40)]:
        stueck = grau[ky:ky + th, kx:kx + tb]
        abw = stueck.std()
        if abw > 8:
            ncc = float(((stueck - stueck.mean()) * taste).mean() / abw)
            if ncc > wert:
                wert, y, x = ncc, int(ky), int(kx)
    if wert < 0.6:
        return None
    mitte_y = y0 + y + th / 2
    blase = _skaliert(_BLASE, hoehe)
    bx = int(x0 + x + tb / 2 + BLASE_ABSTAND * breite - blase.shape[1] / 2 - 6 * k)
    by = int(mitte_y - blase.shape[0] / 2 - 6 * k)
    feld = klein[max(0, by):by + blase.shape[0] + int(12 * k),
                 max(0, bx):bx + blase.shape[1] + int(12 * k)].astype(np.float32).min(axis=2)
    wert_blase = _beste_ncc(feld, blase)[0]
    wert_truhe = _beste_ncc(feld, _skaliert(_TRUHE_F, hoehe))[0]
    return {'y': mitte_y / hoehe, 'gespraech': wert_blase >= .7 and wert_blase >= wert_truhe + .1,
            'truhe': wert_truhe >= .8}


def dialog_signatur(klein):
    """Fingerabdruck der Dialogzeile aus der weißen Schrift (Anteil weißer Pixel je Zelle):
    Hintergrundbewegung ändert ihn kaum, eine neue Zeile deutlich."""
    hoehe, breite = klein.shape[:2]
    band = klein[int(hoehe*0.80):int(hoehe*0.93), int(breite*0.2):int(breite*0.8)].min(axis=2) > 200
    zh, zb = band.shape[0] // 4, band.shape[1] // 8
    return band[:zh * 4, :zb * 8].reshape(zh, 4, zb, 8).mean(axis=(1, 3)).astype(np.float32)


def dialog_ausschnitt(voll):
    """Sprechername + Dialogzeile in voller Auflösung zum Vorlesen lassen."""
    hoehe, breite = voll.shape[:2]
    return np.ascontiguousarray(voll[int(hoehe*0.78):int(hoehe*0.94), int(breite*0.18):int(breite*0.82), :3])


class Fall:
    """Mehrere HUD-freie Weltbereiche müssen gemeinsam nach oben wandern.

    Minimap, Questtext und Teamleiste blieben früher im Phasenvergleich stehen
    und überstimmten den tatsächlichen Fall. Gleichzeitiges seitliches Lenken
    darf eine übereinstimmende Abwärtsbewegung der Kamera nicht verdecken.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.vorher = None
        self.folge = 0
        self.zeit = None
        self.messung = {'felder': 0, 'aufwaerts': 0, 'dy': None}

    def update(self, klein):
        hoehe, breite = klein.shape[:2]
        jetzt = time.monotonic()
        bereiche = ((.03, .43, .28, .79), (.27, .15, .39, .43),
                    (.67, .15, .82, .46), (.67, .55, .82, .79))
        felder = []
        for x0, y0, x1, y1 in bereiche:
            feld = klein[int(y0*hoehe):int(y1*hoehe):2,
                         int(x0*breite):int(x1*breite):2].astype(np.float32).mean(axis=2)
            felder.append(feld - feld.mean())
        werte = []
        if self.vorher is not None and self.zeit is not None and jetzt-self.zeit < .8:
            for vorher, feld in zip(self.vorher, felder):
                if feld.std() < 4:
                    continue
                wert = verschiebung(vorher, feld)
                if wert is not None and wert[2] > 8:
                    werte.append(wert)
        self.vorher, self.zeit = felder, jetzt
        grenze = 1.5 * hoehe / 540
        auf = [w for w in werte if w[1] <= -grenze and abs(w[1]) >= .30*abs(w[0])]
        self.messung = {'felder': len(werte), 'aufwaerts': len(auf),
                        'dy': float(np.median([w[1] for w in auf])) if auf else None}
        faellt = len(auf) >= 2 and len(auf) >= len(werte)*.6
        self.folge = self.folge+1 if faellt else 0
        # Drei starke unabhängige Messungen erlauben schon beim ersten guten
        # Bildpaar zu reagieren; schwächere Fälle verlangen zwei Bildpaare.
        stark = len(auf) >= 3 and self.messung['dy'] <= -4*hoehe/540
        return faellt and (stark or self.folge >= 2)


def karte_ausschneiden(bild):
    """Quadratischer Ausschnitt um die Minimap und (Mitte x, Mitte y, Radius) darin."""
    hoehe = bild.shape[0]
    cx, cy, r = KARTE_X * hoehe, KARTE_Y * hoehe, KARTE_R * hoehe
    rand = r * 1.15
    x0, y0 = int(max(0, cx - rand)), int(max(0, cy - rand))
    return bild[y0:int(cy + rand), x0:int(cx + rand), :3], (cx - x0, cy - y0, r)


def questziel(bild, farbe='gold'):
    """Questsymbol auf der Minimap: (richtung_grad, abstand 0..~1.1) oder None."""
    ausschnitt, (cx, cy, r) = karte_ausschneiden(bild)
    h0, h1, s_min, v_min = FARBEN[farbe]
    h, s, v = _hsv(ausschnitt)
    ys, xs = np.mgrid[:ausschnitt.shape[0], :ausschnitt.shape[1]]
    abstand = np.hypot(xs - cx, ys - cy) / r
    maske = (h >= h0) & (h <= h1) & (s >= s_min) & (v >= v_min) & (abstand < 1.12)
    # Ganzes Symbol ~90-210 Pixel (1080p), halb unter dem Spielerpfeil ~50.
    if maske.sum() < max(4, int((r / 16) ** 2)):
        return None
    py, px = np.nonzero(maske)
    dx, dy = px.mean() - cx, py.mean() - cy
    return (math.degrees(math.atan2(dx, -dy)) % 360, float(math.hypot(dx, dy) / r))


def kegel(bild, breite=80):
    """Kamerarichtung aus dem hellen Sichtkegel der Minimap (Grad) oder None."""
    ausschnitt, (cx, cy, r) = karte_ausschneiden(bild)
    weiss = ausschnitt.astype(np.float32).min(axis=2)  # weiße Überlagerung hebt den kleinsten Kanal
    schritte = 120
    winkel = np.arange(schritte) * 360 / schritte
    radien = np.linspace(0.3, 0.65, 12) * r
    t = np.radians(winkel)[:, None]
    xs = np.clip(np.round(cx + np.sin(t) * radien), 0, weiss.shape[1] - 1).astype(int)
    ys = np.clip(np.round(cy - np.cos(t) * radien), 0, weiss.shape[0] - 1).astype(int)
    profil = weiss[ys, xs].mean(axis=1)
    k = int(round(breite / 360 * schritte))
    summe = np.convolve(np.concatenate([profil, profil[:k - 1]]), np.ones(k), 'valid')[:schritte]
    abstand = summe / k - (profil.sum() - summe) / (schritte - k)
    i = int(abstand.argmax())
    if abstand[i] < 15:
        return None
    return float((winkel[i] + breite / 2) % 360)


def karte_grau(bild):
    """Graustufen-Ring der Minimap ohne Mitte (Pfeil/Sichtkegel bleiben stehen)."""
    ausschnitt, (cx, cy, r) = karte_ausschneiden(bild)
    grau = ausschnitt.astype(np.float32).mean(axis=2)
    ys, xs = np.mgrid[:grau.shape[0], :grau.shape[1]]
    abstand = np.hypot(xs - cx, ys - cy) / r
    gewicht = ((abstand > 0.28) & (abstand < 0.85)).astype(np.float32)
    return (grau - grau[gewicht > 0].mean()) * gewicht


def verschiebung(vorher, jetzt):
    """Wie weit der Karteninhalt gewandert ist (dx, dy, güte) per Phasenkorrelation."""
    if vorher is None or vorher.shape != jetzt.shape:
        return None
    a, b = np.fft.fft2(vorher), np.fft.fft2(jetzt)
    kreuz = np.conj(a) * b
    kreuz /= np.maximum(np.abs(kreuz), 1e-6)
    feld = np.abs(np.fft.ifft2(kreuz))
    py, px = np.unravel_index(int(feld.argmax()), feld.shape)
    hoehe, breite = feld.shape
    dy = py - hoehe if py > hoehe // 2 else py
    dx = px - breite if px > breite // 2 else px
    return float(dx), float(dy), float(feld.max() / (feld.mean() + 1e-9))


def _seiten(klein):
    """Linkes und rechtes Bilddrittel grob in Grau (ohne eigene Figur in der Mitte)."""
    hoehe, breite = klein.shape[:2]
    teil = klein[int(hoehe*0.15):int(hoehe*0.8):4, :, :].astype(np.float32).mean(axis=2)
    return np.concatenate([teil[:, :int(breite*0.3):4], teil[:, int(breite*0.7)::4]], axis=1)


class Bewegung:
    """Hat sich die Figur in der letzten guten Sekunde bewegt? True/False/None (unbekannt)."""

    def __init__(self, uhr=time.monotonic, fenster=1.2):
        self.uhr = uhr
        self.fenster = fenster
        self.verlauf = deque()
        self.wert = None

    def update(self, klein, voll):
        jetzt = self.uhr()
        if self.verlauf and jetzt - self.verlauf[-1][0] < 0.2:
            return self.wert
        eintrag = (jetzt, karte_grau(voll), _seiten(klein))
        self.verlauf.append(eintrag)
        while len(self.verlauf) > 2 and jetzt - self.verlauf[1][0] >= self.fenster:
            self.verlauf.popleft()
        alt = self.verlauf[0]
        if jetzt - alt[0] < self.fenster * 0.8:
            self.wert = None
            return None
        wert = verschiebung(alt[1], eintrag[1])
        bild = float(np.abs(alt[2] - eintrag[2]).mean())
        if wert is not None and wert[2] > 8 and math.hypot(wert[0], wert[1]) <= 40:
            # Karte mit Struktur (Oberwelt): 1,5 px in 1,2 s reichen als Bewegung.
            self.wert = math.hypot(wert[0], wert[1]) >= 1.5 or bild > 12
        else:
            # Leere Karte (Domäne): nur das Bild selbst zählt.
            self.wert = bild > 2.5
        return self.wert


def gegner(bild):
    """Gegner-Lebensbalken nach echtem Vorbild (960x540: ~70x6 px, RGB ~247/95/92, weißes
    „Lv. N“ darüber). Fahnen, Feuerlinien am Boden und Fackeln haben keine Schrift darüber
    oder sind schräg/dick. Liefert (x, y, breite) relativ des mittigsten Balkens oder None."""
    hoehe, breite = bild.shape[:2]
    k = hoehe / 540
    rgb = bild.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Neutrales Rot (Grün ≈ Blau); Flammen und leuchtende Ornamente sind orange (Grün ≫ Blau).
    erlaubt = _hud_maske(hoehe, breite)
    # Vor uns stehen die Gegner gerade in der bisher als eigene Figur maskierten
    # Bildmitte. Ihre Balken verschwanden dadurch nach erfolgreichem Ausrichten.
    erlaubt[int(.12*hoehe):int(.60*hoehe), int(.30*breite):int(.70*breite)] = True
    erlaubt[int(.30*hoehe):int(.60*hoehe), int(.04*breite):int(.30*breite)] = True
    rot = (r > 190) & (r-g > 80) & (r-b > 80) & (np.abs(g-b) < 40) & erlaubt
    # Reines Weiß der Levelschrift, kein gelbliches Glühen.
    weiss = (rgb.min(axis=2) > 180) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)
    lang = max(6, round(10 * k))
    lauf = rot[:, :breite - lang + 1].copy()
    for versatz in range(1, lang):
        lauf &= rot[:, versatz:breite - lang + 1 + versatz]
    kandidaten = np.argwhere(lauf)
    beste = None
    for y, x in kandidaten[::max(1, len(kandidaten) // 80)]:
        mitte = x + lang // 2
        oben = y
        while oben > 0 and rot[oben - 1, mitte] and y - oben < 12 * k:
            oben -= 1
        unten = y
        while unten < hoehe - 1 and rot[unten + 1, mitte] and unten - y < 12 * k:
            unten += 1
        dicke = unten - oben + 1
        if not 3 * k <= dicke <= 8 * k:
            continue
        rand = round(2 * k)
        if oben - rand < 0 or unten + rand >= hoehe:
            continue
        # Flaches Band: knapp darüber und darunter kein Rot.
        if rot[oben - rand, x:x + lang].mean() > 0.3 or rot[unten + rand, x:x + lang].mean() > 0.3:
            continue
        # Weiße Levelschrift über dem Balken.
        schrift = weiss[max(0, oben - round(16 * k)):oben - rand, max(0, x - round(10 * k)):x + round(70 * k)]
        if schrift.sum() < 25 * k * k:
            continue
        # Das alte Ergebnis benutzte nur einen 10-Pixel-Ausschnitt statt der
        # Balkenmitte. Damit wurde häufig seitlich am Gegner vorbeigezielt.
        zeile = rot[(oben+unten)//2]
        links = rechts = int(mitte)
        while links > 0 and zeile[links-1]:
            links -= 1
        while rechts+1 < breite and zeile[rechts+1]:
            rechts += 1
        if rechts-links+1 < lang:
            continue
        ort = ((links+rechts)/2/breite, (oben+unten)/2/hoehe, (rechts-links+1)/breite)
        if beste is None or abs(ort[0] - 0.5) < abs(beste[0] - 0.5):
            beste = ort
    return beste


_RAUTE_FFT = {}


def raute(klein, *, weltkarte=False):
    """Goldene Quest-Raute: (x, y, güte) relativ, oder None.

    weltkarte nur nach bestätigter Kartenerkennung verwenden: Dort gibt es keine
    Minimap/Teamleiste, und die Raute ist beim Einblenden deutlich dunkler.
    """
    # Auf der Karte nur tatsächliche Bedienelemente ausnehmen, nicht den oberen
    # Kartenrand: Pardis Dhyai lag im Fehlerbild bei x=.382/y=.089.
    feld = _raute_ncc(klein, weltkarte, [(0, 0, .19, .30), (.48, 0, 1, .07), (0, .92, 1, 1)]
                      if weltkarte else RAUTE_AUSSEN)
    if feld is None:
        return None
    ncc, th, tb = feld
    hoehe, breite = klein.shape[:2]
    y, x = np.unravel_index(int(ncc.argmax()), ncc.shape)
    guete = float(ncc[y, x])
    if guete < 0.55:
        return None
    return ((x + tb / 2) / breite, (y + th / 2) / hoehe, guete)


def quest_randmarker(klein):
    """Weltkarte: Questziel außerhalb des Ausschnitts. Genshin zeigt es dann als goldene Raute
    in einem dunklen Kreis nahe dem Bildrand – auch über Banner und Hinweisliste links oben
    (Livebild 22:58, Inazuma -> „Go to the Grand Bazaar“ 7 km). Ein Klick darauf springt mit der
    Karte zum Ziel. Das echte Questsymbol steht frei auf der Karte, ohne dunklen Kreis.
    (x, y, güte) relativ oder None."""
    feld = _raute_ncc(klein, True, [(.48, 0, 1, .07), (0, .92, 1, 1)])
    if feld is None:
        return None
    ncc, th, tb = feld
    hoehe, breite = klein.shape[:2]
    k = hoehe / 540
    hell = klein.astype(np.int16).max(axis=2)
    halb = int(18 * k) + 1
    yy, xx = np.mgrid[-halb:halb + 1, -halb:halb + 1]
    r = np.hypot(yy, xx)
    ring = (r >= 14 * k) & (r <= 17 * k)  # dunkler Kreis um die Raute
    for _ in range(6):
        y, x = np.unravel_index(int(ncc.argmax()), ncc.shape)
        guete = float(ncc[y, x])
        if guete < 0.55:
            return None
        ncc[max(0, y - th):y + th, max(0, x - tb):x + tb] = -1
        cx, cy = int(x + tb / 2), int(y + th / 2)
        if not (halb <= cx < breite - halb and halb <= cy < hoehe - halb):
            continue
        rx, ry = cx / breite, cy / hoehe
        if .2 <= rx <= .8 and .18 <= ry <= .82:
            continue  # Randsymbole sitzen nahe am Bildrand
        # Ring dunkel: Randsymbol 0,67, freies Questsymbol auf der Karte höchstens 0,12.
        dunkel = hell[cy - halb:cy + halb + 1, cx - halb:cx + halb + 1][ring]
        if float((dunkel < 90).mean()) >= .5:
            return rx, ry, guete
    return None


def _raute_ncc(klein, weltkarte, aussen):
    """Korrelation der Goldmaske mit der Raute; (ncc, th, tb) oder None ohne genug Gold."""
    hoehe, breite = klein.shape[:2]
    vorlage = _RAUTE
    if abs(hoehe - 540) > 2:
        from PIL import Image
        faktor = hoehe / 540
        groesse = (max(8, round(vorlage.shape[1] * faktor)), max(8, round(vorlage.shape[0] * faktor)))
        vorlage = np.asarray(Image.fromarray(vorlage).resize(groesse))
        vorlage = (vorlage - vorlage.mean()) / vorlage.std()
    # Goldmaske ohne HSV-Umrechnung: Farbton 30-60° heißt r >= g > b und 2(g-b) >= (r-b);
    # Sättigung > 0,65 (b < 0,35 r) trennt die Raute (0,75-0,88) von leuchtenden Ornamenten (~0,6).
    rgb = klein.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maske = ((r >= g) & (g > b) & (2 * (g - b) >= (r - b)) & (20 * b < 7 * r)
             & (r > (130 if weltkarte else 190))).astype(np.float32)
    for x0, y0, x1, y1 in aussen:
        maske[int(y0*hoehe):int(y1*hoehe), int(x0*breite):int(x1*breite)] = 0
    th, tb = vorlage.shape
    n = th * tb
    integral = np.pad(maske.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    summe = integral[th:, tb:] - integral[:-th, tb:] - integral[th:, :-tb] + integral[:-th, :-tb]
    if summe.max() < 0.25 * n * 0.45:  # nicht genug Gold für eine Raute
        return None
    flaeche = summe / n
    # Kreuzkorrelation per FFT (schnelle Größen, Vorlage zwischengespeichert);
    # Maske ist 0/1, daher Streuung = sqrt(p - p²).
    form = (-(-(hoehe + th) // 64) * 64, -(-(breite + tb) // 64) * 64)
    schluessel = (form, vorlage.shape)
    if schluessel not in _RAUTE_FFT:
        _RAUTE_FFT[schluessel] = np.conj(np.fft.rfft2(vorlage, form))
    korrelation = np.fft.irfft2(np.fft.rfft2(maske, form) * _RAUTE_FFT[schluessel], form)
    korrelation = korrelation[:summe.shape[0], :summe.shape[1]]
    streuung = np.sqrt(np.maximum(flaeche - flaeche ** 2, 1e-6))
    ncc = korrelation / (n * streuung)
    ncc[(summe < 0.25 * n * 0.45) | (summe > n * 0.6)] = -1
    return ncc, th, tb


def dialog(bild):
    """Dialogband unten: abgedunkelt und mit weißer Schrift."""
    hoehe, breite = bild.shape[:2]
    band = bild[int(hoehe*0.80):int(hoehe*0.93), int(breite*0.25):int(breite*0.75)].astype(np.int16)
    hell = band.mean(axis=2)
    weiss = ((band.min(axis=2) > 215)).mean()
    return float(np.median(hell)) < 75 and 0.004 < weiss < 0.12


def ladebild(bild):
    """Fast überall dieselbe Farbe (schwarzer/weißer Ladebildschirm)."""
    klein = bild[::4, ::4].reshape(-1, 3).astype(np.int16)
    median = np.median(klein, axis=0)
    return float((np.abs(klein - median).max(axis=1) < 14).mean()) > 0.8


def analysieren(klein, voll, farbe, bewegung, fall=None):
    """Alle Erkennungen auf einmal (für Tests und Einzelbilder)."""
    analyse = Analyse(farbe)
    analyse.bewegung = bewegung
    if fall is not None:
        analyse.fall = fall
    return analyse(klein, voll, alles=True)


class Analyse:
    """Erkennungen pro Bild. Die teuren Suchen (Raute, Gegner, Spur) laufen reihum je eine pro
    Bild, dazwischen gilt das letzte Ergebnis; '..._frisch' sagt, ob es aus diesem Bild stammt
    (gelenkt wird nur mit frischen Positionen, sonst dreht der Pilot doppelt)."""

    def __init__(self, farbe='gold', uhr=time.monotonic):
        self.uhr = uhr
        self.kampf_bis = -1e9
        self.quest_zuletzt = -1e9
        self.farbe = farbe
        self.bewegung = Bewegung(uhr=uhr)
        self.fall = Fall()
        self.takt = 0
        self.merk = {'raute': None, 'gegner': None, 'spur': None, 'pfeile': [], 'truhe': None}
        self.kampfziel = False
        self.gegner_roh = None       # unbestätigter Balken aus dem letzten geprüften Bild
        self.gegner_zuletzt = -1e9   # Gegner oder Pfeile zuletzt gesehen
        self.spuren = deque(maxlen=5)

    def __call__(self, klein, voll, alles=False):
        self.takt += 1
        hud = hud_sichtbar(voll, klein)
        ziel = questziel(voll, self.farbe) if hud else None
        if ziel is not None:
            self.quest_zuletzt = self.uhr()
        im_gleiten = hud and gleitet(klein)
        am_klettern = hud and klettert(klein)
        faellt = self.fall.update(klein) if hud and not am_klettern else False
        if am_klettern:
            self.fall.reset()
        # Ladebild zuerst: sein Tipp-Text unten sah für die Textband-Regel wie ein Dialog aus.
        laden = not hud and ladebild(klein)
        # Dialog: „Auto“-Knopf links oben; ist er ausgegraut (Antwortoptionen auf hellem Himmel),
        # die Symbole daneben oder die F-Taste an einer Antwort; dunkles Textband als Ersatz.
        option = dialog_option(klein) if not hud and not laden else None
        im_dialog = not hud and not laden and (dialog_auto(klein) > 0.65 or dialog_symbole(klein)
                                                or option is not None or dialog(klein))
        menue = not hud and not im_dialog and not laden and menue_x(klein)
        reihe = self.takt % 3
        frisch = {'raute': alles or reihe == 0, 'gegner': alles or reihe == 1, 'spur': alles or reihe == 2}
        if self.uhr() < self.kampf_bis:
            frisch['gegner'] = True  # im Kampf jedes Bild statt jedes dritte Bild prüfen
        if not hud or im_gleiten or faellt:
            self.merk = {'raute': None, 'gegner': None, 'spur': None, 'pfeile': [], 'truhe': None}
            self.spuren.clear()
            if not hud:
                self.fall.reset()
                self.quest_zuletzt = -1e9
            self.kampf_bis = -1e9
        else:
            if frisch['raute']:
                # Raute in der Welt nur, wenn die Minimap kein Questsymbol zeigt (Domänen).
                self.merk['raute'] = raute(klein) if ziel is None else None
                self.merk['truhe'] = truhe(klein)
            # Questtracker ändert sich selten: nach Gegnerkontakt jedes 3. Bild, sonst jedes 10.
            if alles or self.takt % (3 if self.uhr() - self.gegner_zuletzt < 90 else 10) == 0:
                self.kampfziel = kampfziel(klein)
            if frisch['gegner']:
                # Ein Balken zählt erst, wenn er im nächsten geprüften Bild an etwa derselben Stelle
                # wieder da ist: Glanzlichter auf roten Felsen (Natlan, Livelauf 22:58) flackern, echte
                # Gegnerbalken nicht. Einzelbilder (alles=True) bleiben sofort gültig.
                roh = gegner(klein)
                vorher, self.gegner_roh = self.gegner_roh, roh
                bestaetigt = (roh is not None and vorher is not None
                              and abs(roh[0] - vorher[0]) < .12 and abs(roh[1] - vorher[1]) < .12)
                self.merk['gegner'] = roh if (bestaetigt or alles) else None
                if roh is not None:
                    self.kampf_bis = max(self.kampf_bis, self.uhr() + 1)  # nächstes Bild sofort prüfen
                self.merk['pfeile'] = gegner_pfeile(klein)
                if self.merk['gegner'] is not None or self.merk['pfeile']:
                    self.gegner_zuletzt = self.uhr()
                if self.merk['gegner'] is not None or self.merk['pfeile'] or self.kampfziel:
                    self.kampf_bis = self.uhr()+4
            if frisch['spur']:
                # Glitzerspur nur in der Oberwelt mit Questziel (in Domänen sprühen Fackeln Funken)
                # und erst, wenn sie in 3 der letzten 5 Messungen da war.
                self.spuren.append(spur(klein) if ziel is not None or self.uhr()-self.quest_zuletzt < 3 else None)
                gesehen = [s for s in self.spuren if s is not None]
                self.merk['spur'] = gesehen[-1] if (len(gesehen) >= 3 or alles) and self.spuren[-1] else None
        return {'hud': hud,
                'ziel': ziel,
                'raute': self.merk['raute'], 'raute_frisch': frisch['raute'],
                'truhe': self.merk.get('truhe'), 'truhe_frisch': frisch['raute'],
                'gegner': self.merk['gegner'], 'gegner_frisch': frisch['gegner'],
                'pfeile': self.merk['pfeile'],
                'herausforderung': hud and herausforderung(klein),
                'kampfziel': hud and self.kampfziel,
                # Q-Knopf und Teamleiste zählen nur im Kampf (dann ist kampf_bis gesetzt).
                'q_bereit': hud and (alles or self.uhr() < self.kampf_bis) and q_bereit(klein),
                **dict(zip(('team_aktiv', 'team_q'), team_status(klein)
                           if hud and (alles or self.uhr() < self.kampf_bis) else (None, ()))),
                'spur': self.merk['spur'], 'spur_frisch': frisch['spur'],
                'kegel': kegel(voll) if hud else None,
                'f_hinweis': f_hinweis(klein) if hud else None,
                'klettert': am_klettern,
                'faellt': faellt,
                'gleitet': im_gleiten,
                'gleiter_zu': hud and not im_gleiten and faehigkeitstaste_sichtbar(klein),
                'fall_messung': dict(self.fall.messung),
                'eigene_hp': eigene_hp(klein) if hud else None,
                'dialog': im_dialog,
                'dialog_option': option,
                'menue_x': menue,
                # Einfarbige Wand vor der Kamera ist kein Ladebild: nur ohne HUD.
                'laden': laden,
                'bewegt': self.bewegung.update(klein, voll)}


def erkunden_ankunft():
    import erkunden
    return erkunden.ANKUNFT


class Pilot:
    """Zustandsmaschine. tick() liefert Befehle:
    ('halten', taste) / ('loslassen', taste) / ('tippen', taste[, sekunden]) / ('blick', dx, dy) / ('klick',).
    """

    def __init__(self, empfindlichkeit=1100, uhr=time.monotonic, team=None, teleport=False):
        self.zaehler_pro_grad = max(1.0, empfindlichkeit / 100)  # wird bei jeder Drehung nachgelernt
        self.messungen = deque(maxlen=9)
        self.team = team or {}
        self.teleport_erlaubt = teleport
        self.raute_versuche = 0
        self.uhr = uhr
        self.gehalten = set()
        self.zuletzt = {}
        self.modus = 'start'
        self.drehung = None          # (zeit, kegel_vorher, dx) der letzten Kameradrehung
        self.dialog_bis = -1e9       # Dialog gilt kurz nach letzter Erkennung weiter
        self.dialog_aktiv = False
        self.dialog_ende = -1e9
        self.wiederholt = False
        self.weg_von_npc = False
        self.f_sperre_bis = -1e9
        self.w_seit = None
        self.stillstand_seit = None
        self.befreiungen = 0
        self.drehsinn = 1
        self.overlay_seit = None
        self.escapes = 0
        self.am_ziel = False
        self.ankunft = None
        self.f_versuche = 0
        self.suchrunde = 0
        self.such_bis = -1e9
        self.such_kurs = 0.0
        self.fall_seit = None        # Beginn des aktuellen Falls (für genau einen Gleiter-Sprung)
        self.gleiter_offen_zuletzt = -1e9  # Gleiter zuletzt offen gesehen (gegen Flackern)
        self.luft_still_seit = None
        self.gleiter_versuche = 0
        self.gleiter_versuch_zeit = -1e9
        self.hp_vorher = None
        self.hp_verlust_bis = -1e9
        self.kampf_dauer = None
        self.gegner_breite = None
        self.gegner_position = None
        self.gegner_zuletzt_gesehen = -1e9
        self.gegner_fortschritt = -1e9
        self.annaehern_bis = -1e9
        self.ausweichseite = 'a'
        self.figur = 1               # aktuelle Figur im Kampf (Reihum-Wechsel)
        self.umsehen = 0             # Rundumblicke in dieser Kampfphase (begrenzt)
        self.pfeil_dreh = 0          # Drehungen zu Rand-Pfeilen in dieser Kampfphase (begrenzt)
        self.fest_zeit = -1e9        # zuletzt festgesteckt (Spur-Umwege dann unbegrenzt)
        self.spur_umweg_seit = None  # Beginn eines Spur-Umwegs weg vom Ziel (max. 8 s)
        self.spur_gesehen = -1e9
        self.spur_bis = -1e9         # so lange der Spur folgen, nachdem er festhing
        self.spur_kurs = None
        self.spur_kurs_zeit = -1e9
        self.spur_suche_bis = -1e9
        self.umweg = None
        self.umweg_versuche = 0
        self.fern_seit = None        # seit wann das Questziel am Minimap-Rand steht (Teleport)
        self.letzter_teleport = -1e9
        self.kletter_seit = None     # Beginn des aktuellen Kletterns
        self.kletter_versuche = 0
        self.kampf_bis = -1e9        # Kampfbereitschaft nach dem letzten gesehenen Gegner
        self.kampfziel_bis = -1e9    # „Defeat …“ im Questtracker zuletzt gesehen (+3 s)
        self.pfeile_zuletzt = -1e9   # Gegnerpfeile zuletzt gesehen
        self.gegner_kurs = None      # Kamerakurs zum zuletzt gesehenen Gegner (für die Suche)
        self.such_schritt = 0        # Suchrunde bei offenem Kampfziel (drehen, hingehen, umsehen)
        self.e_zeit = -1e9           # letzte E-Taste: Q erst nach der E-Animation
        self.e_faellig = False       # neuer Kampf: zuerst E mit der aktuellen Figur
        self.truhe_seit = None       # Beginn des Wegs zur sichtbaren Truhe (höchstens 40 s)
        self.truhe_sperre_bis = -1e9  # unerreichbare Truhe: 2 min nicht mehr ansteuern
        self.truhe_zuletzt = -1e9    # Truhe oder Truhen-Hinweis zuletzt gesehen
        self.objekt_f = deque(maxlen=12)  # F-Drücke an Truhen/Beute (Begrenzung)
        self.objekt_sperre_bis = -1e9
        self.schnelle_teleports = 0  # Wiederholungen, weil die Karte nicht aufging
        self.erkunder = None         # Erkundungsmodus (erkunden.Erkunder) oder None
        self.erkunden_tick = None
        self.erkunden_suche_seit = None
        self.info_dialog_bereit = True

    def _faellig(self, name, abstand):
        jetzt = self.uhr()
        if jetzt - self.zuletzt.get(name, -1e9) >= abstand:
            self.zuletzt[name] = jetzt
            return True
        return False

    def _halten(self, taste, an):
        if an and taste not in self.gehalten:
            self.gehalten.add(taste)
            if taste == 'w':
                self.w_seit = self.uhr()
            return [('halten', taste)]
        if not an and taste in self.gehalten:
            self.gehalten.discard(taste)
            if taste == 'w':
                self.w_seit = None
            return [('loslassen', taste)]
        return []

    def alles_loslassen(self):
        befehle = [('loslassen', t) for t in sorted(self.gehalten)]
        self.gehalten.clear()
        self.w_seit = None
        return befehle

    def tick(self, info, hinweis=None):
        """info aus analysieren(); hinweis = KI-Einschätzung (mit 'ziel_kurs', 'alter') oder None."""
        jetzt = self.uhr()
        hinweis = hinweis or {}
        # Mitlesen: erst weiterklicken, wenn Gemma die aktuelle Zeile gelesen hat (App setzt das).
        self.info_dialog_bereit = info.get('dialog_bereit', True)
        if info['laden']:
            self.fall_seit = self.luft_still_seit = None
            self.umweg = self.spur_kurs = None
            self.modus = 'laden'
            return self.alles_loslassen()
        # Dialog mit 1,5 s Nachlauf gegen Flackern.
        if info['dialog']:
            self.fall_seit = self.luft_still_seit = None
            self.umweg = self.spur_kurs = None
            self.dialog_bis = jetzt + 1.5
        if jetzt < self.dialog_bis:
            return self._dialog(jetzt, info['dialog'], info.get('dialog_option') is not None)
        if self.dialog_aktiv:
            self._dialog_vorbei(jetzt)
        if not info['hud']:
            return self._overlay(jetzt, info.get('menue_x', False))
        self.overlay_seit = None
        self.escapes = 0
        self._kalibrieren(info, jetzt)
        luft = self._gleiten(info, jetzt)
        if luft is not None:
            return luft
        return self._spielen(info, hinweis, jetzt)

    def _spielen(self, info, hinweis, jetzt):
        # Kampf nur bei echten Lebensbalken oder Rand-Pfeilen im Bild: Gemma erfindet Kämpfe.
        # Danach 4 s Kampfbereitschaft, auch wenn der Balken kurz verschwindet (Gegner springt
        # einen an, Balken außerhalb des Bildes) – sonst springt er zwischen Kampf und Laufen.
        pfeile = info.get('pfeile') or []
        hp = info.get('eigene_hp')
        if hp is not None:
            if self.hp_vorher is not None and hp < self.hp_vorher-.04:
                self.hp_verlust_bis = jetzt+1
            self.hp_vorher = hp
        # Kampfziel im Questtracker („Defeat all opponents 0/6“): Es sind noch Gegner übrig. Bindet
        # ihn aber nur, wenn er in den letzten 90 s Gegner oder Pfeile gesehen hat – sonst stehen
        # sie woanders und er muss erst zum Questziel (Livelauf 22:10: lief bei 0/6 einfach weg).
        if info.get('kampfziel'):
            self.kampfziel_bis = jetzt + 3
        if pfeile:
            self.pfeile_zuletzt = jetzt
        kampfziel = (jetzt < self.kampfziel_bis
                     and jetzt - max(self.gegner_zuletzt_gesehen, self.pfeile_zuletzt) < 90)
        vorher_bis = self.kampf_bis
        if info['gegner'] is not None:
            self.kampf_bis = jetzt + 3
            self.gegner_zuletzt_gesehen = jetzt
            self.umsehen = self.pfeil_dreh = 0
            self.such_schritt = 0
            if info.get('kegel') is not None:
                self.gegner_kurs = (info['kegel'] + bildwinkel(info['gegner'][0])) % 360
        elif pfeile and (self.pfeil_dreh < 6 or kampfziel):
            self.kampf_bis = max(self.kampf_bis, jetzt + 3)
        if info.get('herausforderung') or kampfziel:
            self.kampf_bis = max(self.kampf_bis, jetzt + 1.5)  # „Opponents Defeated x/9“ läuft
        if jetzt < self.kampf_bis and jetzt > vorher_bis + 5:
            # Neuer Kampf: erst E mit der aktuellen Figur, gewechselt wird frühestens nach 4 s
            # (früher sofort – Ventis bereites Q blieb dabei liegen, Livelauf 22:10:02).
            self.e_faellig = True
            self.zuletzt['wechsel'] = jetzt - 3
        if info['gegner'] is not None:
            return self._kampf(info, jetzt)
        if jetzt < self.kampf_bis:
            return self._kampf_suchen(info, pfeile, jetzt)
        # Außerhalb des Kampfes mit sehr wenig HP (Livelauf 22:57: 12 % beim Erkunden): andere Figur
        # nehmen – jede Figur hat eigene HP, der nächste Kampf träfe sonst die angeschlagene.
        hp = info.get('eigene_hp')
        if hp is not None and hp < .3 and self._faellig('wenig_hp_wechsel', 12):
            platz = min(max(self.team) if self.team else 4, 4)
            self.figur = self.figur % max(2, platz) + 1
            self.modus = f'wenig HP: Figur {self.figur}'
            return self._halten('w', False) + [('tippen', str(self.figur))]
        # Truhen immer öffnen (Nikola, 23:01): Truhen- und Beute-Hinweise sofort, sichtbares
        # Truhensymbol ansteuern – beides vor Teleport und Questlauf (er wollte wegteleportieren).
        objekt = self._objekt_f(info, jetzt)
        if objekt is not None:
            return objekt
        if info.get('truhe') is not None and jetzt > self.truhe_sperre_bis:
            return self._zur_truhe(info, jetzt)
        self.truhe_seit = None
        # Auch an einer Wand muss ein fernes Questziel einen Teleport auslösen
        # können. Früher war die Prüfung hinter dem frühen Kletter-Return.
        if self.erkunder is None:  # Erkundung wählt ihre Ziele selbst, kein Quest-Teleport
            teleport = self._teleport_pruefen(info, jetzt)
            if teleport is not None:
                return teleport
        if info.get('klettert'):
            return self._klettern(info, jetzt)
        if jetzt - self.zuletzt.get('klettert', -1e9) > 30:
            self.kletter_versuche = 0  # 30 s ohne Wand: wieder normal kurz klettern
        if self.weg_von_npc:
            # Endlosgespräch: umdrehen und ein Stück weglaufen, bevor neu gelenkt wird.
            self.weg_von_npc = False
            self.modus = 'weg vom NPC'
            return self.alles_loslassen() + [('blick', int(180 * self.zaehler_pro_grad), 0), ('tippen', 'w', 1.5)]
        if self.erkunder is not None:
            return self._erkunden(info, jetzt)
        if info['ziel'] is None and info.get('f_hinweis') is None and (info.get('spur') is not None
                or (self.spur_kurs is not None and jetzt-self.spur_kurs_zeit < 1.5)):
            weg = self._weg_finden(info, jetzt)
            if weg is not None:
                return weg
        if info['ziel'] is not None:
            return self._zum_questziel(info, hinweis, jetzt)
        if info.get('raute') is not None:
            return self._zur_raute(info, hinweis, jetzt)
        return self._ohne_ziel(info, hinweis, jetzt)

    def _klettern(self, info, jetzt):
        """An der Wand: kurz weiterklettern (W), dann mit X absteigen und seitlich umgehen.
        Leertaste wäre hier ein Kletter-Sprung nach oben – deshalb kein normales Befreien.
        Nach drei vergeblichen Umwegen darf er länger klettern (manchmal muss man hoch)."""
        if self.kletter_seit is None or jetzt - self.zuletzt.get('klettert', -1e9) > 3:
            self.kletter_seit = jetzt
        self.zuletzt['klettert'] = jetzt
        erlaubt = 30 if self.kletter_versuche >= 3 else 6
        if jetzt - self.kletter_seit > erlaubt:
            self.kletter_versuche += 1
            self.kletter_seit = None
            self.drehsinn = -self.drehsinn
            self.drehung = None
            self.modus = 'absteigen + umgehen'
            if info.get('ziel') is not None:
                self.befreiungen += 1
                frei = self.alles_loslassen()
                umweg = self._umweg_starten(info, jetzt)
                return frei + [('tippen', 'x'), ('warten', .35)] + umweg
            return (self.alles_loslassen() + [('tippen', 'x'), ('warten', .35)]
                    + self._drehen(80 * self.drehsinn, info, jetzt))
        self.modus = 'klettert'
        return self._halten('w', True)

    def _gleiten(self, info, jetzt):
        """Luftsteuerung hat Vorrang vor Kampf, Festhängen, F und Teleport."""
        if info.get('klettert'):
            self.fall_seit = None
            self.luft_still_seit = None
            return None
        fall, offen = info.get('faellt', False), info.get('gleitet', False)
        befehle = []
        if offen:
            self.gleiter_offen_zuletzt = jetzt
        if fall or offen:
            self.luft_still_seit = None
            if self.fall_seit is None:
                self.fall_seit = jetzt
                self.gleiter_versuche = 0
            # War der Gleiter eben noch offen, ist „zu“ meist nur Flackern der Erkennung –
            # Leertaste würde ihn dann zuklappen (Fallschaden, Livelauf 23:19).
            if fall and not offen and jetzt - getattr(self, 'gleiter_offen_zuletzt', -1e9) > 1.5 and (self.gleiter_versuche == 0 or
                    (self.gleiter_versuche == 1 and info.get('gleiter_zu')
                     and jetzt-self.gleiter_versuch_zeit >= .5)):
                self.gleiter_versuche += 1
                self.gleiter_versuch_zeit = jetzt
                befehle.append(('tippen', 'space'))
        elif self.fall_seit is not None:
            if self.luft_still_seit is None:
                self.luft_still_seit = jetzt
            if jetzt-self.luft_still_seit >= .8:
                self.fall_seit = self.luft_still_seit = None
                return None
        else:
            return None
        self.modus = 'gleiten' if offen else 'Gleiter öffnen/prüfen'
        for taste in tuple(self.gehalten):
            if taste != 'w':
                befehle += self._halten(taste, False)
        ziel = info.get('ziel')
        if ziel is not None:
            fehler = winkel_diff(ziel[0], info['kegel']) if info.get('kegel') is not None else 0
            if abs(fehler) > 8 and self.drehung is None:
                befehle += self._drehen(float(np.clip(fehler, -30, 30)), info, jetzt)
            befehle += self._halten('w', ziel[1] > .12 and abs(fehler) < 65)
        else:
            befehle += self._halten('w', False)
        return befehle

    def _interaktion(self, info, jetzt, am_ziel=False):
        """F nur bei sichtbarem Hinweis. Sprechblase (Gespräch) nur am Questziel – sonst würde
        er jeden Passanten und die Begleiterin ansprechen. Truhen, Gegenstände, Mechanismen sofort."""
        hinweis_f = info.get('f_hinweis')
        if hinweis_f is None or jetzt <= self.f_sperre_bis:
            return []
        if hinweis_f['gespraech'] and not am_ziel:
            return []
        if not hinweis_f['gespraech'] and jetzt < self.objekt_sperre_bis:
            return []  # Pause nach 10 F ohne Wirkung gilt auch hier
        if self._faellig('interagieren', 1.2):
            self.modus = 'Gespräch' if hinweis_f['gespraech'] else 'F: öffnen/aufheben'
            return [('tippen', 'f')]
        return []

    # --- Dialoge, Menüs ---------------------------------------------------

    def _dialog(self, jetzt, sichtbar=True, option=False):
        if not sichtbar:
            # Nachlauf gegen Flackern: Modus halten, aber nichts drücken – sonst spricht F nach
            # Dialogende gleich den nächsten NPC an (Behnam zweimal hintereinander).
            self.modus = 'dialog'
            return self.alles_loslassen()
        if not self.dialog_aktiv:
            self.dialog_aktiv = True
            # Endlosschleife mit einem NPC: neues Gespräch kurz nach dem letzten, das er selbst mit F
            # begonnen hat. (Story-Dialoge folgen oft schnell aufeinander – das ist keine Schleife.)
            self.wiederholt = (jetzt - self.dialog_ende < 12
                               and jetzt - self.zuletzt.get('interagieren', -1e9) < 3)
        self.modus = 'dialog'
        befehle = self.alles_loslassen()
        if not self.info_dialog_bereit:
            self.modus = 'dialog (liest mit)'
            return befehle
        if option:
            # Antwortoption sichtbar: F wählt die markierte (erste) Antwort.
            self.modus = 'dialog (Antwort)'
            if self._faellig('dialog', 0.6):
                befehle.append(('tippen', 'f'))
            return befehle
        if self._faellig('dialog', 0.5):
            # Leertaste setzt Zeilen fort, F wählt die erste Antwort.
            wechsel = self.zuletzt.get('dialog_wechsel', 0)
            self.zuletzt['dialog_wechsel'] = 1 - wechsel
            befehle.append(('tippen', 'f') if wechsel else ('tippen', 'space'))
        return befehle

    def _dialog_vorbei(self, jetzt):
        self.dialog_aktiv = False
        self.dialog_ende = jetzt
        # Nach jedem Gespräch kurz kein F; bei Wiederholung lange Sperre + wegdrehen.
        self.f_sperre_bis = jetzt + (45 if self.wiederholt else 8)
        self.weg_von_npc = self.wiederholt

    def _overlay(self, jetzt, menue_x=False):
        """Keine Karte, kein HP-Balken: Menü, Hinweisfenster oder Zwischensequenz."""
        self.modus = 'Menü' if menue_x else 'Zwischensequenz'
        befehle = self.alles_loslassen()
        self.drehung = None
        if self.overlay_seit is None:
            self.overlay_seit = jetzt
        # ESC nur bei echtem Menü mit Schließen-X (z. B. versehentlich geöffneter Domänen-Eingang).
        # Zwischensequenzen haben kein X – dort einfach abwarten.
        if menue_x and jetzt - self.overlay_seit >= 2.0 and self.escapes < 6 and self._faellig('escape', 3.0):
            self.escapes += 1
            self.f_sperre_bis = max(self.f_sperre_bis, jetzt + 20)
            befehle.append(('tippen', 'escape'))
        if menue_x and self.escapes >= 6:
            self.modus = 'Menü bleibt offen – bitte selbst schließen'
        return befehle

    # --- Kamera ---------------------------------------------------------------

    def _kalibrieren(self, info, jetzt):
        """Nach einer Drehung am Sichtkegel messen, wie viele Mauszähler ein Grad sind."""
        if self.drehung is None:
            return
        zeit, alt, dx = self.drehung
        if jetzt - zeit < 0.25:
            return
        self.drehung = None
        if jetzt < self.kampf_bis or info.get('gegner') is not None:
            return  # im Kampf dreht die Kamera von allein mit (Angriffe, Ausweichen): nicht lernen
        if alt is None or info['kegel'] is None or jetzt - zeit > 2:
            return
        gemessen = winkel_diff(info['kegel'], alt)
        if abs(dx) < 60 or abs(gemessen) < 10 or (gemessen > 0) != (dx > 0):
            return
        neu = abs(dx) / abs(gemessen)
        if 3 <= neu <= 40:  # Ausreißer (Kegel kurz falsch erkannt, Drehung verschluckt) verwerfen
            self.messungen.append(neu)
            self.zaehler_pro_grad = float(np.median(self.messungen))

    def _drehen(self, grad, info, jetzt):
        dx = int(np.clip(grad * self.zaehler_pro_grad, -3000, 3000))
        self.drehung = (jetzt, info['kegel'], dx)
        return [('blick', dx, 0)]

    def _fahren(self, kurs, info, jetzt):
        """Kamera auf den Kurs drehen (sobald die letzte Drehung gemessen ist) und laufen."""
        befehle, fehler = [], None
        if info['kegel'] is not None:
            fehler = winkel_diff(kurs, info['kegel'])
            if abs(fehler) >= 8 and self.drehung is None:
                befehle += self._drehen(fehler, info, jetzt)
        laufen = fehler is None or abs(fehler) < 60
        befehle += self._halten('w', laufen)
        if laufen:
            befehle += self._festhaengen(info, jetzt)
        return befehle

    def _steckt_fest(self, info, jetzt):
        """W seit über 1,5 s gehalten und 1,5 s lang keine Bewegung."""
        if info['bewegt'] is not False or self.w_seit is None or jetzt - self.w_seit < 1.5:
            self.stillstand_seit = None
            if info['bewegt']:
                self.zuletzt.setdefault('bewegt_seit', jetzt)
                if jetzt - self.zuletzt['bewegt_seit'] > 4:
                    self.befreiungen = 0
                    self.raute_versuche = 0
            return False
        self.zuletzt.pop('bewegt_seit', None)
        if self.stillstand_seit is None:
            self.stillstand_seit = jetzt
            return False
        if jetzt - self.stillstand_seit < 1.5:
            return False
        self.stillstand_seit = None
        return True

    def _festhaengen(self, info, jetzt):
        return self._befreien(info, jetzt) if self._steckt_fest(info, jetzt) else []

    def _befreien(self, info, jetzt):
        self.befreiungen += 1
        self.fest_zeit = jetzt
        if info.get('ziel') is not None:
            return self._umweg_starten(info, jetzt)
        self.modus = 'befreien'
        schritt = self.befreiungen % 4
        if schritt == 1:
            return [('tippen', 'space')]
        if schritt == 2:
            return [('tippen', 'a', 0.7), ('tippen', 'space')]
        if schritt == 3:
            return [('tippen', 'd', 0.7), ('tippen', 'space')]
        self.drehsinn = -self.drehsinn
        return self._drehen(90 * self.drehsinn, info, jetzt) + [('tippen', 'w', 1.0)]

    def _umweg_starten(self, info, jetzt):
        self.umweg_versuche += 1
        self.fest_zeit = jetzt
        seite = 1 if self.umweg_versuche % 2 else -1
        basis = info['ziel'][0] if info.get('ziel') is not None else (info.get('kegel') or 0)
        kurs = (basis + seite*(80 if self.umweg_versuche < 3 else 105)) % 360
        self.umweg = {'kurs': kurs, 'seite': seite, 'start': jetzt,
                      'bis': jetzt+6, 'phase': 0}
        self.spur_kurs = None
        self.modus = 'Hindernis seitlich umgehen'
        self.drehung = None
        fehler = winkel_diff(kurs, info['kegel']) if info.get('kegel') is not None else 80*seite
        return self._halten('w', False) + self._drehen(float(np.clip(fehler, -90, 90)), info, jetzt)

    def _umweg_fahren(self, info, jetzt):
        if self.umweg is None:
            return None
        if jetzt >= self.umweg['bis']:
            if self.umweg['phase'] == 0:
                ziel = info['ziel'][0] if info.get('ziel') is not None else self.umweg['kurs']
                self.umweg.update(kurs=(ziel+self.umweg['seite']*35) % 360,
                                  bis=jetzt+2.5, phase=1)
            else:
                self.umweg = None
                return None
        self.modus = 'Hindernis seitlich umgehen'
        return self._fahren(self.umweg['kurs'], info, jetzt)

    def _spur_passt(self, info, jetzt):
        """Führt die V-Spur ungefähr zum Questziel (≤ 60°), folgt er ihr immer. Führt sie davon weg
        (Umweg um Absperrung oder Pfeiler), höchstens 8 s am Stück, danach 15 s Luftlinie – vor dem
        Kampf drehte er sich sonst zwischen Spur und Ziel im Kreis. Nach Festhängen immer."""
        if jetzt - self.fest_zeit < 25 or info.get('ziel') is None or info.get('kegel') is None:
            return True
        spur_kurs = (info['kegel'] + bildwinkel(info['spur'][0])) % 360
        if abs(winkel_diff(spur_kurs, info['ziel'][0])) <= 60:
            return True
        if self.spur_umweg_seit is None or jetzt - self.spur_umweg_seit > 23:
            self.spur_umweg_seit = jetzt
        return jetzt - self.spur_umweg_seit <= 8

    def _weg_finden(self, info, jetzt):
        # Erst von der Wand lösen. Danach darf eine sichtbare V-Spur den Umweg
        # wieder übernehmen; sie enthält die bessere Information über den Weg.
        if self.umweg is not None and jetzt-self.umweg['start'] < 1.5:
            return self._umweg_fahren(info, jetzt)
        if info.get('spur') is not None and self._spur_passt(info, jetzt):
            self.spur_gesehen = jetzt
            self.modus = 'folgt V-Spur'
            winkel = bildwinkel(info['spur'][0])
            if info.get('spur_frisch', True):
                if info.get('kegel') is not None:
                    self.spur_kurs = (info['kegel']+float(np.clip(winkel*.7, -30, 30))) % 360
                    self.spur_kurs_zeit = jetzt
                self.umweg = None
            if self.spur_kurs is not None:
                return self._fahren(self.spur_kurs, info, jetzt)
            return self._halten('w', abs(winkel) < 40)
        if self.spur_kurs is not None and jetzt-self.spur_kurs_zeit < 1.5:
            self.modus = 'V-Spur kurz verdeckt'
            return self._fahren(self.spur_kurs, info, jetzt)
        umweg = self._umweg_fahren(info, jetzt)
        if umweg is not None:
            return umweg
        intervall = 6 if self.spur_kurs is not None and jetzt-self.spur_gesehen < 20 else 20
        if self._faellig('weg_zeigen', intervall):
            self.spur_suche_bis = jetzt+1.4
            return [('tippen', 'v')] + self._fahren(info['ziel'][0], info, jetzt)
        return None

    # --- Ziele -----------------------------------------------------------------

    def teleport_bald_wieder(self, sekunden=20):
        """Die Karte ging nicht auf (Ruckler, z. B. während das KI-Modell lädt, Livelauf 22:55):
        nach 20 s neu versuchen statt erst nach 3 min – höchstens zweimal hintereinander."""
        if self.schnelle_teleports < 2:
            self.schnelle_teleports += 1
            self.letzter_teleport = self.uhr() - 180 + sekunden

    def _teleport_pruefen(self, info, jetzt):
        # Ziel weit weg (Symbol klebt am Minimap-Rand, gemessen 0,97): nach 8 s teleportieren,
        # höchstens alle 3 min. Nicht direkt nach einer Truhe (Beute liegt noch da).
        if jetzt - self.truhe_zuletzt < 8:
            self.fern_seit = None
            return None
        if jetzt - self.letzter_teleport > 300:
            self.schnelle_teleports = 0
        if info['ziel'] is not None and info['ziel'][1] >= 0.9:
            if self.fern_seit is None:
                self.fern_seit = jetzt
            if (self.teleport_erlaubt and jetzt - self.fern_seit > 8
                    and jetzt - self.letzter_teleport > 180):
                self.letzter_teleport = jetzt
                self.fern_seit = None
                self.drehung = None
                self.modus = 'Teleport'
                return self.alles_loslassen() + [('teleport',)]
        else:
            self.fern_seit = None
        return None

    def _zum_questziel(self, info, hinweis, jetzt):
        richtung, abstand = info['ziel']
        if jetzt < self.such_bis:
            self.modus = 'Umgebung absuchen'
            return self._fahren(self.such_kurs, info, jetzt)
        if abstand < 0.12:
            self.am_ziel = True
        elif abstand > 0.25:
            self.am_ziel = False
            self.ankunft = None
        if self.am_ziel:
            if info.get('f_hinweis') is None and (info.get('spur') is not None or
                    (self.spur_kurs is not None and jetzt-self.spur_kurs_zeit < 1.5)):
                weg = self._weg_finden(info, jetzt)
                if weg is not None:
                    return weg
            return self._am_ziel(info, hinweis, jetzt)
        self.modus = 'laufen'
        befehle = self._weg_finden(info, jetzt)
        if befehle is None:
            self.modus = 'laufen'
            befehle = self._fahren(richtung, info, jetzt)
        return befehle + self._interaktion(info, jetzt, am_ziel=abstand < 0.3)

    def _am_ziel(self, info, hinweis, jetzt):
        """Am Questort: F nur bei sichtbarem Hinweis; passiert nichts (z. B. „Higher 16m“),
        Umgebung absuchen."""
        self.modus = 'am Ziel'
        befehle = self._halten('w', False)
        if self.ankunft is None:
            self.ankunft = jetzt
            self.f_versuche = 0
        if info.get('f_hinweis') is not None and self.f_versuche < 3:
            f = self._interaktion(info, jetzt, am_ziel=True)
            self.f_versuche += len(f)
            if f:
                self.ankunft = jetzt  # nach Interaktion neu abwarten
            return befehle + f
        if jetzt - self.ankunft > 4:
            self.suchrunde += 1
            ki_kurs = hinweis.get('ziel_kurs') if hinweis.get('alter', 99) < 14 else None
            self.such_kurs = ki_kurs if ki_kurs is not None else ((info['kegel'] or 0) + 90 * self.suchrunde) % 360
            self.such_bis = jetzt + 3.0
            self.ankunft = None
            self.am_ziel = False
        return befehle

    def _zur_raute(self, info, hinweis, jetzt):
        """Domäne: goldene Raute in der Welt anlaufen. Geht es nicht weiter (Dornen, Monument,
        Fackel im Weg), Element-Rätselreflex, dann F, dann normal befreien."""
        x = info['raute'][0]
        self.modus = 'zur Raute'
        befehle = []
        winkel = bildwinkel(x)
        if (info.get('raute_frisch', True) and abs(winkel) >= 6 and self.drehung is None
                and self._faellig('raute_lenken', 0.3)):
            befehle += self._drehen(winkel * 0.9, info, jetzt)
        laufen = abs(winkel) < 40
        befehle += self._halten('w', laufen)
        # In Domänen steht an der Raute meist die Questfigur (Amber …): Gespräch erlaubt.
        befehle += self._interaktion(info, jetzt, am_ziel=abs(winkel) < 15)
        if laufen and self._steckt_fest(info, jetzt):
            self.raute_versuche += 1
            stufe = self.raute_versuche % 3
            if stufe == 1:
                befehle += self._element_angriff(hinweis)
            elif stufe == 2:
                befehle += [('tippen', 'space')]
            else:
                befehle += self._befreien(info, jetzt)
        return befehle

    def _element_angriff(self, hinweis):
        """Rätsel-Reflex: aufs passende Element wechseln (aus Gemmas Text, sonst Pyro für Fackeln,
        Dornen, Monumente), dann E und Angriffe Richtung Bildmitte. Mitgelesene Dialoge zählen
        zuerst („Green symbolizes Dendro, which can be ignited by Pyro“)."""
        gelesen = [w for w in reversed(hinweis.get('stichworte', [])) if w in ELEMENTE]  # neuestes zuerst
        beschreibung = str(hinweis.get('state', '')).lower()
        element = gelesen[0] if gelesen else next((e for e in ELEMENTE if e in beschreibung), 'pyro')
        slots = sorted(slot for slot, e in self.team.items() if e == element)
        self.modus = f'Rätsel: {element}-Angriff'
        befehle = self.alles_loslassen()
        if slots:
            befehle += [('tippen', str(slots[0])), ('warten', 0.7)]
        return befehle + [('tippen', 'e'), ('warten', 0.6)] + [('klick',), ('warten', 0.25)] * 4

    def _ohne_ziel(self, info, hinweis, jetzt):
        """Kein Questsymbol (z. B. in Domänen): dem KI-Hinweis folgen, sonst geradeaus erkunden."""
        befehle = self._interaktion(info, jetzt)
        ki_kurs = hinweis.get('ziel_kurs') if hinweis.get('alter', 99) < 14 else None
        if ki_kurs is not None:
            self.modus = 'KI-Ziel'
            return befehle + self._fahren(ki_kurs, info, jetzt)
        self.modus = 'erkunden'
        befehle += self._halten('w', True)
        return befehle + self._festhaengen(info, jetzt)

    # --- Erkundung --------------------------------------------------------------

    def _erkunden(self, info, jetzt):
        """Erkundungsmodus: nächstes Ziel aus der Datenbank (Truhe, Okulus), Kurs per Kompass aus der
        letzten Kartenposition. Neu gepeilt wird nach 25 s Laufzeit und zur Bestätigung am Ziel –
        die App öffnet dafür kurz die Karte (Befehl 'position')."""
        e = self.erkunder
        # Weg nur zählen, wenn er sich wirklich bewegt (feststecken zählte als 5,5 m/s Fortschritt).
        if self.erkunden_tick is not None:
            schritt = min(jetzt - self.erkunden_tick, 1.0)
            e.unterwegs(schritt)
            if 'w' in self.gehalten and info.get('bewegt') is not False:
                e.laufen(schritt)
        self.erkunden_tick = jetzt
        if e.peilung_noetig():
            if self._faellig('peilen', 4):
                self.modus = 'Erkunden: Position auf der Karte bestimmen'
                return self.alles_loslassen() + [('position',)]
            return self._halten('w', False)
        if e.fix is None:
            # Keine Position (Höhle/Untergrund): ein Stück geradeaus, dann erneut peilen.
            self.modus = 'Erkunden: ohne Position weiter'
            return self._halten('w', True) + self._festhaengen(info, jetzt)
        if e.ziel is None and e.ziel_waehlen() is None:
            self.modus = 'Erkunden: nichts Offenes in 400 m'
            return self._halten('w', False)
        if e.ziel_abgelaufen():
            self.modus = f"Erkunden: {e.ziel['typ']} unerreichbar"
            e.erledigen('unerreichbar')
            e.fix = None
            return self._halten('w', False)
        if e.ankunft_bestaetigt:
            return self._am_erkundungsziel(info, jetzt)
        rest = e.abstand()
        self.erkunden_suche_seit = None
        self.modus = f"Erkunden: {e.ziel['typ']} noch ~{round(rest / 25) * 25:.0f} m"
        return self._fahren(e.kurs(), info, jetzt)

    def _am_erkundungsziel(self, info, jetzt):
        """Ankunft per Karte bestätigt (≤ 8 m): erst die geschätzten letzten Meter auf Kurs gehen,
        dann ±5 m Kartenfehler mit einer kleinen Spirale (1 s gehen, 60° drehen) absuchen. Okuli
        sammelt man durch Berühren ein, Truhen öffnet _objekt_f über den F-Hinweis. Dann abhaken."""
        e = self.erkunder
        if (e.abstand() or 0) > 1.5 and self.erkunden_suche_seit is None:
            self.modus = f"Erkunden: letzte Meter ({e.ziel['typ']})"
            return self._fahren(e.kurs(), info, jetzt)
        self.modus = f"Erkunden: am Ziel ({e.ziel['typ']})"
        if self.erkunden_suche_seit is None:
            self.erkunden_suche_seit = jetzt
        dauer = jetzt - self.erkunden_suche_seit
        if dauer > 10:
            e.erledigen('besucht')
            e.fix = None  # Suchweg verfälscht die Koppelnavigation: neu peilen
            self.erkunden_suche_seit = None
            return self._halten('w', False)
        befehle = []
        if self.drehung is None and self._faellig('erkunden_spirale', 1.2):
            befehle += self._drehen(60, info, jetzt)
        return befehle + self._halten('w', True)

    # --- Truhen ----------------------------------------------------------------

    def _objekt_f(self, info, jetzt):
        """F-Hinweis an einer Truhe – oder an Beute bis 30 s nach Kampf/Truhe: stehen bleiben und F,
        auch wenn das Questziel weit weg ist (früher kam zuerst der Teleport). Andere Hinweise
        (Statue, Wegpunkt, Laden) bleiben der normalen Navigation überlassen. Höchstens 10 F in
        15 s, dann 15 s Pause – manche Hinweise bleiben stehen (z. B. voller Rucksack)."""
        f = info.get('f_hinweis')
        if f is None or f['gespraech'] or jetzt <= self.f_sperre_bis or jetzt < self.objekt_sperre_bis:
            return None
        # Am Erkundungsziel auch Sammelobjekte und Statuen (Freischalten per F) – nur an Domänen
        # nicht: F öffnet dort das Domänenmenü, freigeschaltet wird schon durch Annähern.
        am_erkundungsziel = (self.erkunder is not None and self.erkunder.ziel is not None
                             and self.erkunder.ziel['art'] != 'domaene' and (self.erkunder.abstand() or 99) < 30)
        if f.get('truhe'):
            self.truhe_zuletzt = jetzt
        elif jetzt - max(self.gegner_zuletzt_gesehen, self.truhe_zuletzt) > 30 and not am_erkundungsziel:
            return None
        while self.objekt_f and jetzt - self.objekt_f[0] > 15:
            self.objekt_f.popleft()
        if len(self.objekt_f) >= 10:
            self.objekt_sperre_bis = jetzt + 15
            self.objekt_f.clear()
            return None
        self.modus = 'Truhe öffnen' if f.get('truhe') else 'Beute aufheben'
        befehle = self._halten('w', False)
        if self._faellig('objekt_f', .6):
            self.objekt_f.append(jetzt)
            befehle.append(('tippen', 'f'))
        return befehle

    def _zur_truhe(self, info, jetzt):
        """Truhensymbol ansteuern: drehen, bis es vorn ist, und hinlaufen; geöffnet wird über den
        F-Hinweis (_objekt_f). Höchstens 40 s am Stück, dann 2 min Ruhe vor dieser Truhe
        (unerreichbar oder versiegelt)."""
        self.truhe_zuletzt = jetzt
        if self.truhe_seit is None:
            self.truhe_seit = jetzt
        if jetzt - self.truhe_seit > 40:
            self.truhe_sperre_bis = jetzt + 120
            self.truhe_seit = None
            self.modus = 'Truhe unerreichbar'
            return self._halten('w', False)
        self.modus = 'zur Truhe'
        winkel = bildwinkel(info['truhe'][0])
        befehle = []
        if (abs(winkel) > 12 and self.drehung is None and info.get('truhe_frisch', True)
                and self._faellig('truhe_drehen', .6)):
            befehle += self._drehen(winkel, info, jetzt)
        laufen = abs(winkel) < 40
        befehle += self._halten('w', laufen)
        if laufen:
            befehle += self._festhaengen(info, jetzt)
        return befehle

    # --- Kampf -----------------------------------------------------------------

    def _kampf_suchen(self, info, pfeile, jetzt):
        """Kein Lebensbalken im Bild, aber Kampfphase: Erst weiterkämpfen (Gegner ist meist nur kurz
        verdeckt oder direkt neben ihm), dann zu den Warnpfeilen drehen – sie liegen auf einer
        Ellipse um die Figur, unten heißt „hinter ihm“. Ohne Pfeile höchstens dreimal kurz umsehen
        und aufgeben – außer der Questtracker verlangt noch einen Kampf („Defeat all opponents“):
        dann weitersuchen statt zur Quest zu laufen."""
        self.modus = 'kampf (sucht Gegner)'
        befehle = []
        gesehen_vor = jetzt - self.gegner_zuletzt_gesehen
        kampfziel = jetzt < self.kampfziel_bis
        if gesehen_vor < 1.5:
            befehle += self._halten('w', False)
            burst = self._burst(info, jetzt)
            if burst:
                return befehle + burst
            if self._faellig('angriff', .18):
                befehle.append(('klick',))
            return befehle + self._verteidigen(info, jetzt)
        if pfeile and (self.pfeil_dreh < 6 or kampfziel):
            # Mittlere Richtung aller Pfeile (Einheitsvektoren, damit ±180° nicht zu 0° wird).
            winkel = [math.radians(pfeil_winkel(x, y)) for x, y in pfeile]
            grad = math.degrees(math.atan2(sum(map(math.sin, winkel)), sum(map(math.cos, winkel))))
            if abs(grad) > 35:
                self.modus = 'kampf (dreht zum Gegnerpfeil)'  # Richtung steht in der Statuszeile
                befehle += self._halten('w', False)
                if self.drehung is None and self._faellig('zum_pfeil', .8):
                    self.pfeil_dreh += 1
                    befehle += self._drehen(grad, info, jetzt)
            else:
                # Pfeil vorn: Gegner knapp außerhalb des Bildes – hingehen und zuschlagen.
                self.modus = 'kampf (zum Gegnerpfeil)'
                befehle += self._halten('w', True)
                if self._faellig('angriff', .5):
                    befehle.append(('klick',))
            return befehle + self._verteidigen(info, jetzt)
        befehle += self._halten('w', False)
        if kampfziel:
            return befehle + self._kampfziel_suchen(info, jetzt) + self._verteidigen(info, jetzt)
        if self.umsehen < 3 and self.drehung is None and self._faellig('umsehen', 1.2):
            self.umsehen += 1
            befehle += self._drehen(40 * self.drehsinn, info, jetzt)
        elif not pfeile and self.umsehen >= 3 and info.get('herausforderung'):
            if self._faellig('umsehen_pause', 6):
                self.umsehen = 0  # Herausforderung läuft weiter: nach einer Pause erneut umsehen
        elif not pfeile and self.umsehen >= 3 and jetzt > self.kampf_bis - 1.0:
            self.kampf_bis = jetzt  # niemand zu finden: zurück zur Quest
        return befehle + self._verteidigen(info, jetzt)

    def _kampfziel_suchen(self, info, jetzt):
        """Kampfziel offen, aber weder Balken noch Pfeil zu sehen: Runde aus je 1 s – zur letzten
        Gegnerrichtung drehen, 2 s hingehen, dann fünfmal 60° umsehen. Nach 90 s ohne jede
        Gegnerspur gibt _spielen das Kampfziel frei (dann stehen die Gegner woanders)."""
        self.modus = 'kampf (Kampfziel offen, sucht)'
        schritt = self.such_schritt % 8
        if self.drehung is not None or not self._faellig('kampfziel_suche', 1.0):
            return self._halten('w', schritt in (2, 3))
        self.such_schritt += 1
        if schritt == 0:
            if self.gegner_kurs is not None and info.get('kegel') is not None:
                fehler = winkel_diff(self.gegner_kurs, info['kegel'])
                if abs(fehler) > 15:
                    return self._drehen(fehler, info, jetzt)
            return []
        if schritt in (1, 2):
            return self._halten('w', True)
        return self._halten('w', False) + self._drehen(60 * self.drehsinn, info, jetzt)

    def _burst(self, info, jetzt):
        """Q, sobald der Q-Knopf „bereit“ zeigt – frühestens 0,9 s nach E. Früher kam Q 0,25 s nach
        E und ging in der E-Animation verloren (Livelauf 22:10:09: Ventis Q blieb liegen)."""
        if not info.get('q_bereit') or jetzt - self.e_zeit < .9 or not self._faellig('burst', 1.5):
            return []
        self.modus = f'kampf (Q mit Figur {self.figur})'
        return self._halten('w', False) + [('tippen', 'q')]

    def _wechsel(self, info, jetzt):
        """Reihum alle 7 s die Figur wechseln und E nutzen. Leuchtet in der Teamleiste das Q einer
        anderen Figur, ist sie schon nach 2,5 s dran (ihr Q folgt über _burst)."""
        seit = jetzt - self.zuletzt.get('wechsel', -1e9)
        if info.get('team_aktiv') and seit > 1.5:
            self.figur = info['team_aktiv']  # das Spiel weiß es besser (z. B. „Cannot switch“)
        platz = min(max(self.team) if self.team else 4, 4)
        bereit = [p for p in (info.get('team_q') or ()) if p != self.figur and p <= platz]
        if seit < 7 and not (bereit and seit >= 2.5):
            return []
        self.zuletzt['wechsel'] = jetzt
        self.figur = bereit[0] if bereit else self.figur % max(2, platz) + 1
        self.e_zeit = jetzt + .45
        self.modus = f'kampf (Figur {self.figur}' + (', Q bereit)' if bereit else ')')
        return [('tippen', str(self.figur)), ('warten', .45), ('tippen', 'e')]

    def _verteidigen(self, info, jetzt, sucht=False):
        """Kurzer seitlicher Sprint bei Schaden oder sehr niedrigen HP (höchstens alle 2,5-3 s,
        sonst kommt er vor lauter Ausweichen nicht zum Angreifen).

        Das ist defensive Bewegung, keine behauptete Erkennung beliebiger Boss-Projektile.
        """
        hp = info.get('eigene_hp')
        schaden = jetzt < self.hp_verlust_bis
        kritisch = hp is not None and hp < .25
        if not (schaden or kritisch or sucht):
            return []
        abstand = 2.5 if schaden else (3.0 if kritisch else 4.0)
        if not self._faellig('ausweichen', abstand):
            return []
        self.ausweichseite = 'd' if self.ausweichseite == 'a' else 'a'
        self.modus = 'kampf (ausweichen)'
        return self._halten('w', False) + [('ausweichen', self.ausweichseite, .1)]

    def _kampf(self, info, jetzt):
        """Gegner mit Lebensbalken im Bild. Angreifen hat Vorrang: Normalangriffe zielen von allein
        auf den nächsten Gegner, der Balken muss nicht mittig stehen. Gedreht wird nur bei großer
        Abweichung, gelaufen nur zu fernen Gegnern. Q sobald bereit, reihum Figurwechsel mit E – wie
        ein Spieler es tut; im Prüfungs-Kampf meldet das Spiel „Cannot switch“, das schadet nicht."""
        self.modus = 'kampf'
        ziel = info['gegner']
        befehle = []
        ausweichen = self._verteidigen(info, jetzt)
        if ausweichen:
            return ausweichen
        winkel = bildwinkel(ziel[0])
        fern = ziel[1] < .4 and ziel[2] < .04
        if abs(winkel) > 30 and self.drehung is None and info.get('gegner_frisch', True) and self._faellig('zielen', .7):
            self.modus = 'kampf (ausrichten)'
            befehle += self._drehen(float(np.clip(winkel * .8, -45, 45)), info, jetzt)
        laufen = fern and abs(winkel) < 45
        befehle += self._halten('w', laufen)
        if laufen:
            self.modus = 'kampf (annähern)'
            if self._steckt_fest(info, jetzt):
                return befehle + self._verteidigen(info, jetzt, sucht=True)
        if self.e_faellig and not laufen:  # bei fernem Gegner verpufft E: erst in Reichweite
            self.e_faellig = False
            self.e_zeit = jetzt
            self.modus = f'kampf (E mit Figur {self.figur})'
            return befehle + [('tippen', 'e')]
        burst = self._burst(info, jetzt)
        if burst:
            return befehle + burst
        wechsel = self._wechsel(info, jetzt)
        if wechsel:
            return befehle + wechsel
        if not laufen and self._faellig('angriff', .18):
            befehle.append(('klick',))
        return befehle
