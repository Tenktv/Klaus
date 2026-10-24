# Genshin-Modus (experimentell)

Lokales Bildmodell: Ollama `gemma3:4b`. Kein API-Schluessel erforderlich.
Start: `Genshin-Modus.bat` oder in Klaus „oeffne den Genshin-Modus“.
Klaus' Werkzeug oeffnet nur das Panel. Der Spielmodus beginnt erst mit F8/Start.

## Korrektur 0.22: Natlan – kein Luft-Kampf, Position auch in wenig erkundeten Gegenden

Live 22:55-22:59 (Natlan, Atocpan 10 %): „fightet Luft“, keine Truhe gefunden.

- **Gegnerbalken bestaetigen:** Glanzlichter auf roten Felsen sahen aus wie roter Balken mit weisser
  „Lv.“-Schrift. Ein Balken zaehlt jetzt erst, wenn er im naechsten geprueften Bild an etwa derselben
  Stelle wieder da ist (echte Balken stehen, Glanzlichter flackern).
- **Wenig HP ohne Kampf** (< 30 %, Livelauf 12 %): andere Figur nehmen (jede Figur hat eigene HP).
- **Position mit Vorwissen:** Der volle Atlas-Abgleich braucht 6 Symbole mit 2 Statuen – in Natlan
  waren nur 2-5 freie sichtbar (graue Wegpunkte erkennt er nicht als Symbol). Mit geschaetzter
  Position (letzte Peilung + Koppelnavigation) und dem zuletzt gemessenen Massstab genuegt jetzt ein
  Symbol (`kartenatlas.lokalisieren_nahe`): bei 80-150 m Schaetzfehler unter 3 m genau. Einzelne
  Symbole nur bei eindeutiger Zuordnung (naechster Konkurrent >= 160 m weiter; 4 Karten: 0 Fehlgriffe).
- Ohne Vorwissen bis zu 3x herauszoomen, danach wieder auf den alten Zoom (Massstab bleibt gueltig).
- Speicher-Offsets (Nikola, 19.10.) bewusst nicht verwendet: Code-Injektion/Speicherlesen im
  geschuetzten Prozess = Cheat, Kernel-Anti-Cheat erkennt das, Kontosperre wahrscheinlich.

## Korrektur 0.21: Diagnosebilder bleiben, Erkundung robuster

- **Nichts wird mehr geloescht** (Nikola: „die sollen bleiben“). Diagnose- und F10-Bilder liegen in
  `logs/diag/<Datum>/`, der Kampfrekorder in `logs/kampf/<Datum>/`. Vorher blieben nur 40 bzw. 90
  Bilder, und weil die Namen nur Uhrzeiten waren, loeschte die Aufraeumfunktion die heutigen 22:xx-
  Bilder statt der von gestern 23:xx. Die automatischen Bilder vom 19.10. abends sind verloren;
  alle F10-Bilder sind erhalten.
- Zielgrenze (150 s) zaehlt nur Erkundungszeit, keine Kaempfe (Truhen galten nach Kaempfen als
  unerreichbar).
- Position nicht bestimmbar (Hoehle/Untergrund): 15 s weiterlaufen statt alle 4 s Karte oeffnen.
- „freigeschaltet“ nur nach eigenem Besuch; schon freie Punkte bleiben „schon frei“.

## Korrektur 0.20: Erkundung kommt wirklich an

Live 22:28 (Sumeru-Wueste): Er oeffnete alle paar Sekunden die Karte, kam kaum voran (22 m ->
17 m -> 21 m), suchte 17 m neben dem Dendroculus im Kreis („dreht sich im Quadrat“) und hakte ihn ab.

- **Koppelnavigation** zaehlt Weg nur, wenn er sich wirklich bewegt (feststecken galt als 5,5 m/s).
- **Ankunft nur mit Kartenbeweis:** Erst eine Peilung mit <= 8 m (vorher 12 m, Schaetzung genuegte).
  Danach die geschaetzten letzten Meter auf Kurs, dann Spirale; waehrend der Suche keine Peilung.
- Okuli-Hinweise komplett: 901 schwer, 318 leicht, 241 ohne Text. Der Dendroculus aus dem Lauf
  liegt „Below the broken stone wall“ – andere Hoehe als der Charakter auf den Ruinen.
- Offen: weisse Vierzack-Sterne auf der Minimap (Okuli?) – wenn ja, letzte Meter darueber steuern.

## Erweiterung 0.19: Freischalten und schwere Okuli

- **Teleportpunkte, Statuen, Domaenen** (641/62/74 aus kartenatlas.json) sind Erkundungsziele.
  Jeder Kartenblick ordnet die sichtbaren Symbole Atlaspunkten zu (25 m): blau = schon frei
  (abhaken), grau = Ziel. Ist ein besuchter Punkt noch grau, gibt es einen zweiten Versuch.
  Wegpunkte/Domaenen schalten sich beim Annaehern frei, Statuen per F; an Domaenen kein F
  (oeffnet das Domaenenmenue).
- **Pin-Status korrigiert:** Die blaue Raute wurde an einem festen Punkt gesucht – bei anderer
  Zoomstufe galten freie Pins als grau (Inazuma-Karte). Jetzt Blau-Pixel im ganzen Pinkopf:
  frei 18-31, gesperrt 0, dazwischen (Kueste, Questsymbol darueber) „unklar“ und nie Ziel.
- **Schwere Okuli** (Nikola: hoch, Raetsel, kreativ): Der Community-Hinweis entscheidet – Hoehe
  (top, cliff, midair, floating …), Spezialmechanik (launcher, kuuhenki, moonlane, seelie,
  updraft …) oder Sperre (quest, cave, inside, puzzle …) = schwer. Der Erkundungsmodus nimmt nur
  leichte Okuli; die schweren bleiben fuer Claude (F11) mit Hinweis und Fundort-Bild.

## Erweiterung 0.18: Erkundungsmodus (Stufe 1)

Panel-Schalter „Erkunden statt Quest“. Ziele: Truhen und Okuli (Anemo … Luno, 1460 Stueck) aus
`vorlagen/raetsel_atlas.json`, nur oberirdisch, im Umkreis von 400 m. Erledigte Ziele (geoeffnet,
vor Ort nichts gefunden, unerreichbar) stehen in `logs/erkundet.json` und werden nie wieder
angesteuert.

- **Position:** Karte kurz oeffnen (M), Atlas-Abgleich + Spielerpfeil, Karte schliessen (~3 s).
  Gemessen: 1 Atlaseinheit = 1 m (6977 Einheiten fuer „6986m“ Inazuma -> Basar).
- **Weg:** Kompasskurs aus der letzten Position (Karte genordet, Kurs 0 = Norden), Koppel-
  navigation mit gelernter Laufgeschwindigkeit; neu gepeilt nach 25 s Laufzeit und einmal zur
  Bestaetigung der Ankunft (12 m). Kampf, Truhen, F an Sammelobjekten und Klettern haben Vorrang.
- **Vor Ort:** 10 s kleine Spirale (Okuli durch Beruehren, Truhen per F-Hinweis), dann abhaken.
  150 s ohne Ankunft = unerreichbar.
- Noch nicht: Teleport zu fernen Zielen, Raetsel loesen (Hinweise stehen schon in der Bruecke),
  Positionsbestimmung ohne Kartenstopp (Minimap-Abgleich), Okuli an Statuen abgeben.

## Korrektur 0.17: Karte zoomt richtig, Gleiter bleibt offen, Raetsel-Datenbank

Live 23:16/23:18 (Questziel Sumeru-Stadt): Er waehlte die Statue in Vissudha statt eines Wegpunkts
in der Stadt, musste laufen und klettern, Venti starb an Fallschaden.

- **Zoom wirkte nicht.** Ein Zoombefehl war eine Mausrad-Rastung (~2 % Massstab, Zoomregler blieb
  stehen). Jetzt 12 Rastungen je Schritt (`kartensuche.ZOOM_RASTEN`), 1 s Animation.
- **Hineinzoomen am Ziel:** Liegt der beste Wegpunkt weiter als 0,06 Bildhoehen vom Questsymbol,
  wird die Quest zentriert und bis zu 3 Stufen hineingezoomt – Staedte zeigen ihre Wegpunkte erst
  nah. Verschwinden dabei alle Ziele, eine Stufe zurueck.
- **Gleiter:** War er in den letzten 1,5 s offen, gilt „zu“ als Erkennungsflackern – keine
  Leertaste mehr, die ihn zuklappen wuerde. Bei ploetzlichem HP-Sturz (> 15 %) wird eine
  Bildfolge in logs/diag/verlauf gespeichert.
- **Raetsel-Datenbank:** `werkzeuge/raetsel_atlas_laden.py` speichert die oeffentlichen
  HoYoLAB-Kartenpunkte lokal (`vorlagen/raetsel_atlas.json`): 4199 Raetsel in 138 Typen (Seelie,
  Elementar-Monument, Fackel, Druckplatte, Zeitpruefung, Schreine …) mit Community-Hinweis und
  Fundort-Bild, plus 3512 Truhen nach Art. Hinweise sind kurze Notizen, keine Komplettloesungen.
  Die Position kommt vom Spielerpfeil auf der offenen Karte oder vom Teleportziel
  (`raetsel_db.atlas_position`); Raetsel in der Naehe stehen im Protokoll und in der
  F11-Bruecke (`zustand.json`: `position`, `raetsel_in_der_naehe`).
- Weitere Quellen: GenshinSolvers (Apache-2.0) hat Verbindungsdaten und Loeser fuer 55
  Wuerfel-Raetsel in Inazuma (Stand 2022) – Kandidat fuer einen Wuerfel-Befehl der Bruecke.
  Game8 hat ausfuehrliche Textanleitungen, aber keine Schnittstelle: nur gezielt nachschlagen.

## Korrektur 0.16: Truhen immer oeffnen, Teleport in andere Regionen

Live 22:55-23:02 (Inazuma, „Go to the Grand Bazaar“ 7 km, Kampf gut): Nach dem Kampf lag eine
Truhe am Strand, er wollte wegteleportieren; die Kartensuche fand Sumeru nie.

- **Truhen-Hinweis galt als Gespraech.** Das kleine Truhensymbol in „F ▸ Common Chest“ erreichte an
  der Sprechblasen-Vorlage 0,55 (Schwelle war 0,55) – Gespraeche nur am Questziel, also nie F.
  Jetzt: Gespraech nur bei eindeutiger Blase (≥ 0,7 und deutlich ueber dem Truhensymbol;
  echte NPCs 1,00). Alle Truhenarten und Beute zaehlen als Objekt.
- **Truhen immer oeffnen** (Nikola): weisses Truhensymbol in der Welt (mit Entfernung oder am
  Rand mit Pfeil, `vorlagen/truhe_marker.png`, 0,89-1,00 gegen hoechstens 0,77) wird angesteuert,
  F an Truhe und Beute (bis 30 s nach Kampf/Truhe) hat Vorrang vor Teleport und Questlauf.
  Hoechstens 40 s pro Truhe, dann 2 min Ruhe; hoechstens 10 F in 15 s, dann 15 s Pause.
  Kein Teleport bis 8 s nach der letzten Truhe.
- **Ziel in anderer Region:** Auf der Karte zeigt eine goldene Raute im dunklen Kreis am Rand
  (z. B. links oben auf dem Event-Banner) ein Ziel ausserhalb des Ausschnitts. Ein Klick darauf
  springt zum Ziel (Nikola, 23:02). Die Suche klickt es jetzt zuerst; das freie Questsymbol auf der
  Karte hat keinen dunklen Kreis (Ring-Dunkelanteil 0,00-0,12 gegen 0,67).
- **Herausgezoomte Karte galt als geschlossen** (Zoomregler 0,60-0,74 < 0,75): Suche brach nach
  dem Zoomen ab. Schwelle 0,5 – andere Menues mit X hoechstens 0,17.
- **Karte ging nicht auf** (22:55, vermutlich Ruckler, waehrend das KI-Modell 15 s lud – die Karte
  kam ~8 s spaeter): bis zu 20 Bilder (10 s) warten, Diagnosebild speichern, neuer Versuch nach 20 s.

## Korrektur 0.15: Kampfziel halten, Warnpfeile rundum, Q nutzen

Live 22:10 („Defeat all opponents 0/6“): Nach 30 s Kampf verlor er die Balken, sah sich dreimal um
und lief zum 1344 m entfernten Questmarker – die Gegner jagten ihn (HP 28k -> 18k). Ventis Q war
ab 22:09:59 bereit und wurde nie ausgeloest. Ursachen und Aenderungen:

- **Warnpfeile hinter ihm unsichtbar.** Genshin zeichnet sie auf einer Ellipse um die Bildmitte
  (Halbachsen 26,6 % Breite / 37 % Hoehe); hinten = unter der Figur. Genau diese Zone (Bildmitte,
  untere HUD-Leiste) war gesperrt, und auf Gras sind sie korallrot (255/100/95) statt rosa.
  Jetzt: Suche nur im Ring um die Ellipse, Farbe rosa oder korallrot, Dichte auf der engen Box,
  drei Konturvorlagen (gefuellt, mit Kerbe, hinten). Er dreht um den Winkel des Pfeils
  (`pfeil_winkel`: 0 vorn, ±180 hinten); Pfeil vorn = hingehen und zuschlagen.
- **Kampfziel im Questtracker** („Defeat …“ am Zeilenanfang, auch unterstrichen bei Hauptquests,
  Vorlage `vorlagen/kampfziel.png`, geglaettet verglichen): Solange es dasteht und er in den letzten
  90 s Gegner oder Pfeile gesehen hat, bleibt er im Kampf – kein Questlauf, keine V-Spur, kein
  Teleport. Suchrunde: zur letzten Gegnerrichtung drehen, 2 s hingehen, fuenfmal 60° umsehen.
  Ohne Gegnerkontakt bindet es nicht (dann stehen die Gegner noch am Questziel).
- **Q:** Der Q-Knopf ist bereit ein deckendes, leuchtendes Symbol (Kontrast 64-84), sonst
  durchscheinend oder Abklingsekunden (≤ 54). Q sobald bereit, fruehestens 0,9 s nach E (vorher
  0,25 s – die E-Animation schluckte den Druck). Leuchtet in der Teamleiste das Q einer anderen
  Figur, wechselt er schon nach 2,5 s zu ihr. Die aktive Figur liest er am grauen Nummernfeld ab.
- **Kampfbeginn:** erst E mit der aktuellen Figur (sobald der Gegner in Reichweite ist),
  gewechselt wird fruehestens nach 4 s – vorher sofort, dabei blieb Ventis bereites Q liegen.
- Statuszeile: Gegnerpfeile mit Richtung, „Kampfziel offen“, „Q bereit“; Kampfrekorder schreibt
  zusaetzlich `kampfziel`, `q_bereit`, `team_aktiv`, `team_q`.

## Korrektur 0.14: Kampf nach Kampfrekorder und Nikolas Referenzkampf

Live 21:54: HP 63 % -> 5 %, fast kein Angriff, Kamera drehte staendig. Ursachen und Aenderungen:

- **Angreifen hat Vorrang.** Vorher nur bei Balken < 8° mittig und ohne laufende Drehung –
  bei mehreren beweglichen Gegnern fast nie. Normalangriffe zielen in Genshin von allein auf den
  naechsten Gegner; gedreht wird nur ab 30° Abweichung (hoechstens alle 0,7 s), gelaufen nur zu
  fernen Gegnern (kleiner Balken). Kein „erst annaehern“ mehr (Venti ist Bogenschuetze).
- **Figurwechsel reihum** alle 7 s (1-4, dann E und Q) – wie Nikola im Referenzkampf (Hu Tao,
  Vodyanitsa, Qiqi, Venti; Verdampfen). In Pruefungen meldet das Spiel „Cannot switch“, harmlos.
- **Gegner kurz verloren:** 1,5 s weiter angreifen (meist nur verdeckt), Rand-Pfeilen hoechstens
  6x folgen, hoechstens dreimal 40° umsehen, Kampfphase endet 3 s nach dem letzten Balken.
  Vorher 60° alle 0,7 s blind = „Spinnen“.
- **Ausweichen** nur bei Schaden (alle 2,5 s) oder HP < 25 % (alle 3 s), nicht wegen Pfeilen.
- **Lenkung lernt nicht im Kampf** (sprang 4,4 -> 27,5 Zaehler/Grad, Drehungen viel zu klein/gross).
- **V-Spur:** zeigt sie ungefaehr zum Ziel (≤ 60°), immer folgen; Umweg weg vom Ziel hoechstens
  8 s am Stueck, dann 15 s Luftlinie (vor dem Kampf pendelte die Kamera 46°-121° bei Ziel 355°).
- **Kampfrekorder:** jede Sekunde Bild + Zeile in `logs/kampf/` und `logs/kampf.jsonl`.

## Korrektur 0.13: Luft, Kampf und V-Spur

- **Fallen/Gleiten:** vier HUD-freie Bildbereiche statt statischer Team-/Questanzeigen
  fuer die Bewegungsmessung. Der geoeffnete Gleiter wird am Leertasten-Symbol
  erkannt. Luftsteuerung hat Vorrang vor Angriffen, Ausweichen, Spruengen und
  Teleport. Kein wiederholtes Space bei schon offenem Gleiter; maximal ein
  Wiederholversuch nur bei weiterem Fall und bestaetigter normaler E-Tastenanzeige.
- **Kampf:** echte rosa Richtungspfeile links unter dem Questtext werden nicht
  mehr weggeschnitten. Gegnerbalken duerfen in der Bildmitte liegen; gezielt wird
  auf ihre Mitte. Im Kampf wird jedes Bild neu geprueft. Erst ausrichten, dann
  kontrolliert annaehern und angreifen. Ohne frisches Ziel keine Blindangriffe.
- **Abwehr:** kurze seitliche Sprints bei HP-Verlust, kritischen HP oder nur per
  Pfeil sichtbaren Angreifern, mit begrenzter Haeufigkeit. Bei weit entfernten
  Gegnern seitlich ausweichen und Distanz schliessen. Das ist keine vollstaendige
  Erkennung beliebiger Projektile oder Boss-Angriffsphasen; solche Kaempfe sind
  nicht als verlaesslich autonom bestaetigt.
- **Weg:** V-Navigation frueh anfordern; bestaetigte Funkenketten haben Vorrang vor
  der Luftlinie. Naechsten Spurabschnitt statt entferntestem Funken waehlen und
  bei kurzer Verdeckung den Kurs halten. Hindernisumwege bleiben mehrere Sekunden
  aktiv; ein weiterer Fehlversuch wechselt die Seite. Kein vollstaendiges
  dreidimensionales Strassen-/Gebaeude-Navmesh.
- Kurze Diagnosefolgen bei Luft-/Ausweichereignissen bzw. F10 unter
  `logs/diag/verlauf/` (maximal sechs Folgen pro Lauf, je sechs vorausgehende
  Spielbilder; Speichern nebenlaeufig).

Der Teleport wurde im echten Lauf am 18.10.2026 um 20:42:18 ausgeloest; der Nutzer
bestaetigt den erfolgreichen Teleport. Neuer autonomer Luft-/Kampf-/Weg-Livetest
mit 0.13 steht noch aus. Zum Laden: F9, altes Agentenfenster schliessen und neu
starten; der Fenstertitel muss **0.13** zeigen.

## Erweiterung 0.12: Kartensuche und Statuen

- Wegpunkte **und Statuen der Sieben** zaehlen als Teleportziele. Graue Symbole
  gelten weiter als gesperrt; F wird nur bei sichtbarem Teleport-Knopf gedrueckt.
- Wenn kein freier Punkt direkt am Questziel liegt, duerfen auch weiter entfernte
  freie Ziele gewaehlt werden, sofern ein eindeutig erkannter Spielerpfeil
  mindestens 20 Prozent kuerzere Kartenstrecke belegt. Das ist Luftlinie auf der
  Karte, keine Zusage ueber Berg-/Strassenwege. Ohne passende Freischaltung laeuft er weiter.
- Fehlt ein Ziel, wird die Karte zentriert, bis zu drei Rastungen herausgezoomt
  und in bis zu 25 ueberlappenden Ausschnitten abgesucht (60 Sekunden Limit).
  Nach jedem Verschieben/Zoom entstehen neue Bildkoordinaten.
- Das ist eine begrenzte Suche im geoeffneten Kartengebiet, keine Garantie fuer
  alle Untergrundebenen, Sonderkarten oder saemtliche Weltregionen.
- Die Kartenerkennung bleibt auch bei ausgeblendeten Wegpunkt-Symbolen aktiv,
  wenn Schliessen-X und Zoomregler zusammen erkannt werden.
- Rosa Begleiter werden per Pfeilkontur von echten Gegner-Richtungspfeilen getrennt.
- Fokusverlust und F9 brechen Kartenbewegungen ab und lassen die Maustaste los.
- Lokaler Atlas aus der offiziellen HoYoLAB-Webkarte: 801 oeffentliche
  Kartenpunkte (Abruf 18.10.2026), davon 641 Wegpunkte und 62 Statuen fuer den
  geometrischen Abgleich. Kein Login oder API-Schluessel, keine automatische
  Bildschirmuebertragung an HoYoLAB. Der Lauf verwendet die gespeicherten Daten.
- Mindestens sechs passende Symbole, darunter zwei Statuen, und eindeutige
  Zuordnung sind noetig. Auf vier echten Karten wurden 21-37 Symbole mit etwa
  1,1 Pixel Abweichung zugeordnet. Der Atlas kann angrenzende Suchbereiche
  vorschlagen; anklickbar werden Ziele erst durch frische Erkennung im Spiel.
  Atlasdaten enthalten keine Freischaltungen des Accounts.

Quelle: [HoYoLAB Teyvat Interactive Map](https://act.hoyolab.com/ys/app/interactive-map/index.html?lang=en-us).
Die gespeicherte Datei `vorlagen/kartenatlas.json` enthaelt die genaue
oeffentliche Datenquelle. Andere Ebenen/Sonderkarten brauchen weiterhin eigene Erkennung.

Zum Laden der aktuellen Version: F9, Genshin-Modus-Fenster schliessen und neu starten.
Kein Neustart der gesamten Klaus-App noetig.

## Korrektur 0.11: Teleport-Ziel am Kartenrand

Am Diagnosebild `F10_192459.png` reproduziert: Pardis Dhyai ist oben auf der
Weltkarte sichtbar, aber die Spielwelt-Maske blendete die oberen 10 Prozent aus.
Zusaetzlich lag das dunklere Gold unter dem Helligkeitsfilter. Die bestaetigte
Weltkarte verwendet jetzt eine eigene Bereichsmaske und Helligkeitsschwelle;
die Erkennung in der Spielwelt bleibt unveraendert.

- Bis zu drei frische Kartenbilder beim Einblenden; danach begrenzter Abbruch.
- Bei fehlendem Questzeichen wird das Kartenbild mit Diagnosegrund gespeichert.
- Teleportpruefung auch beim Klettern, weiterhin nicht im Kampf und mit 3 Minuten Abstand.
- Abgebrochene F-Bestaetigung meldet keinen Erfolg; Fokus/Stopp wird vor Kartenaufnahmen geprueft.
- 137 bestehende/erweiterte Tests plus 4 Ablauf-Tests bestanden (141 insgesamt).
  Das echte Fehlerbild wird mit geschwaerzter UID als Regression verwendet.
  Kein neuer Live-Teleport nach dieser Aenderung nachgewiesen.

## Autopilot (ab 0.3, Standard)

Zwei Schleifen gleichzeitig statt „erst denken, dann handeln“:

- **Reflexe** (`src/genshin_agent/reflexe.py`, ~8x pro Sekunde, ~22 ms pro Bild):
  - *Steuerbar?* Minimap-„N“ (Mustervergleich) oder gruener eigener HP-Balken sichtbar.
    Fehlt beides und ist es weder Dialog noch Ladebild: Menue/Hinweisfenster → nach 2 s ESC
    (hoechstens 6x), danach 20 s kein F. Das schliesst z. B. versehentlich geoeffnete Domaenen-Eingaenge.
  - *Navigation:* Minimap ist genordet. Questrichtung = Winkel des goldenen Questsymbols,
    Kamerarichtung = heller Sichtkegel. Lenken = Kamera um die Differenz drehen; die Mauszaehler
    pro Grad werden nach jeder Drehung am Kegel nachgelernt („Lenkung x/°“ im Protokoll).
  - *Am Ziel:* bis zu 3x F, passiert nichts (z. B. „Higher 16m“): 3 s in eine Suchrichtung laufen
    (KI-Hinweis oder +90° je Runde), zurueck, erneut versuchen. Gegen Waende laufen = klettern.
  - *Domaenen:* Minimap leer, aber die **goldene Quest-Raute** steht in der Spielwelt
    (Mustervergleich, ~40 ms). Hinlaufen; geht es nicht weiter (Dornen, Monument, Fackel):
    Element-Raetselreflex = auf die passende Figur wechseln (Element aus Gemmas Text, sonst Pyro),
    E + Angriffe Richtung Raute; danach F/Springen, dann normal befreien.
  - *Ohne Questsymbol und ohne Raute:* dem KI-Hinweis folgen, sonst geradeaus erkunden; alle 2,5 s F.
    Zeigt Gemma viermal fast gleich (typisch x=0.20), wird ihr Zeigen ignoriert.
  - **Dialoge** erkennt er am „▶ Auto“-Knopf links oben (auch in hellen Szenen; frueher wurden
    die als Menue behandelt und mit ESC beantwortet). Ist „Auto“ bei Antwortoptionen ausgegraut
    und auf hellem Himmel unsichtbar, an Auge-/Lautsprecher-Symbol daneben oder an der F-Taste der
    Antwort (x≈0,64); dann waehlt er mit F. Ladebilder (Tipp-Text unten) haben Vorrang. Gemma liest jede Zeile (Sprecher + Text)
    → `logs/dialoge.txt` und Panel („💬 Candace: …“). Er klickt im Takt weiter (Leertaste/F),
    vorgelesen wird nebenher aus einer Warteschlange – auf Gemma zu warten (10-20 s pro Zeile bei
    laufendem Spiel) liess Dialoge stehen. Neue Zeile = andere weisse Schrift (Hintergrund egal).
    Element-/Raetselwoerter daraus steuern den Element-Reflex.
    Nach jedem Gespraech 8 s F-Sperre. Endlosschleife (45 s + wegdrehen) nur, wenn er das neue
    Gespraech selbst kurz vorher mit F begonnen hat – Story-Dialoge folgen oft schnell aufeinander.
  - **ESC** nur bei Menues mit Schliessen-X oben rechts (Karte, Questbuch, Domaenen-Eingang);
    Zwischensequenzen haben kein X und werden abgewartet.
  - **F nur bei sichtbarem F-Hinweis** (Vorlage aus echtem Bild). Sprechblase = NPC → nur am
    Questziel; Truhen, Gegenstaende, Mechanismen → sofort. Er sucht keine Truhen, oeffnet aber
    alle, an denen er vorbeikommt.
  - **Glitzerspur (V):** nur wenn die Luftlinie nicht weiterkommt (kuerzlich festgesteckt), folgt
    er der goldenen Questnavigation (fuehrt um Mauern herum). Sonnige Glanzpunkte (Marktstaende)
    sahen sonst wie Funken aus; die Ausdauer-Anzeige faellt durch Farbe und Ausblendung heraus.
    V nur festgesteckt und hoechstens einmal pro Minute (V schaltet womoeglich um). Nicht in Domaenen.
  - **Teleportieren:** steht das Questsymbol 8 s am Minimap-Rand (weit weg), oeffnet er die Karte
    (M), sucht das goldene Questsymbol, klickt den naechsten **freigeschalteten** Teleportpunkt
    daneben (weisser Pin, hellblaue Raute; graue = gesperrt), bei Auswahlliste den neuen Pin-Eintrag
    „Teleport Waypoint“, und drueckt F, aber nur, wenn der „Teleport“-Knopf erkannt ist. Sonst ESC.
    Hoechstens alle 3 Minuten; im Panel abschaltbar. („Navigate“ im Questbuch oeffnet die Karte nicht.)
    Vorlagen: `src/genshin_agent/vorlagen/`.
  - **Gleiten:** faellt er (Welt rutscht im Bild nach oben), einmal Leertaste = Gleiter, weiter
    lenken. Noch nicht live geprueft.
  - Teure Erkennungen (Raute, Gegner, Spur) laufen reihum, ~65-90 ms pro Bild bei 1080p.
  - Gegner = roter Balken (~70x6 px bei 960x540) **mit weisser „Lv.“-Schrift darueber**; Fahnen,
    Feuerlinien und Fackeln zaehlen nicht. Gemmas Kampfmeldungen werden ignoriert (erfunden).
    Kampf: hinlaufen, Angriff, E, Q – kein Figurwechsel.
    Gegner ausserhalb des Bildes zeigt Genshin mit **rosa Rand-Pfeilen** (Blau > Gruen, kompakt;
    Feuer und Lebensbalken haben Blau ≤ Gruen, die Blase ueber der Figur ist ausgeblendet): dorthin
    drehen. Nach jedem gesehenen Gegner 4 s Kampfbereitschaft (angreifen, umsehen) statt sofort
    weiterzulaufen. **Kampf-Herausforderung** (Stoppuhr oben Mitte, „Opponents Defeated x/9“):
    so lange suchen und kaempfen, kein Laufen/Teleport zum Questziel.
  - Stillstand trotz W (Karte bewegt sich 1,2 s nicht) → springen/ausweichen/drehen.
  - **Klettern** (Anzeige „Absteigen [X]“ unten rechts): hoechstens 6 s weiterklettern, dann X,
    100° zur Seite drehen, 2 s laufen (Umweg); nach drei vergeblichen Umwegen bis 30 s klettern.
    Beim Klettern keine Leertaste (das waere ein Kletter-Sprung nach oben).
  - Questsymbol auf der Minimap nur aus sehr sattem, hellem Gold (Saettigung ≥ 0,7): Wuestensand
    in Sumeru ist auch goldgelb und verzog Richtung (217° statt 188°) und Abstand (0,64 statt 0,97).
  - Lenkung (Mauszaehler pro Grad): Median der letzten 9 plausiblen Messungen (3-40), Start 11.
- **Claude-Steuerung (F11)** fuer Raetsel – wirkt nur, wenn Claude im Chat gerade aktiv spielt
  (F11 druecken UND Claude „uebernimm“ schreiben). Autopilot und Gemma pausieren, das Panel legt
  `logs/bruecke/bild.jpg` + `zustand.json` ab und fuehrt Befehlsdateien `befehl_N.json` aus
  (`src/genshin_agent/fertigkeiten.py`: drehen, zielen, hingehen, interagieren, angreifen mit
  Element, gleiten, Figur …; nur Whitelist, Zeit-/Winkelgrenzen, alles-oder-nichts).
  Claudes Seite: `python src/genshin_agent/bruecke_cli.py status|senden|hilfe`. Befehle aelter
  als 30 s oder ohne Spiel im Vordergrund werden verworfen, nie verspaetet ausgefuehrt.
  Team-Elemente im Panel („1=anemo 2=pyro …“) bestimmen, wer bei „element“ eingewechselt wird.
- **KI** (Gemma im Hintergrund, ~7 s pro Bild): drueckt keine Tasten, sondern zeigt, wohin es
  geht (horizontale Bildposition von Tuer/Konsole/NPC/Gang). Zusammen mit der Kamerarichtung beim
  Aufnehmen wird daraus eine feste Himmelsrichtung. Hinweise gelten 14 Sekunden.
- Fokusverlust pausiert statt abzubrechen; Laufzeit bis 60 Minuten.
- Questfarbe (gold = Archon, lila = Story, blau = Welt) im Panel waehlbar. Die
  Kamera-Empfindlichkeit ist nur der Startwert fuer das Nachlernen.
- Alle 45 s ein verkleinertes Spielbild + Minimap in 1080p + Erkennungswerte nach `logs/diag/`.
  **F10** speichert sofort das volle Spielbild (fuer gezielte Nachkalibrierung).
  Nur bei aktivem Spielfenster.
- Regressionstests mit echten Spielbildern: `tests/genshin_bilder/` (UID geschwaerzt).
- „Als Admin neu starten“ im Panel loest die UIPI-Sperre (UAC-Abfrage bestaetigst du selbst).

## Nachgewiesene Ursache auf diesem PC

Am 18.10.2026 hatte Genshin Windows-Integritaetsstufe 12288 (hoch), der Agent
8192 (mittel). Windows UIPI blockiert diese Eingaben. Der bisherige Text
„Testeingabe gesendet“ war kein Nachweis fuer eine Bewegung im Spiel.

Falls dieser Konflikt gemeldet wird: normales Spielpanel schliessen und
`Genshin-Modus-als-Admin.bat` selbst starten. Windows zeigt eine UAC-Abfrage.
Nur der kleine Spielmodus wird erhoeht; die Klaus-Hauptanwendung bleibt normal.
Die UAC-Abfrage muss der Benutzer selbst beantworten. Kein Treiber, keine
Anti-Cheat-Umgehung. Annahme durch Windows garantiert keine Annahme im Spiel.

## Bedienung

- Erst „Bewegung testen“ und binnen fuenf Sekunden ins Spiel wechseln.
- F8 startet bis zu 100 Entscheidungen, maximal zehn Minuten.
- F9/STOP beendet Eingaben. Klaus' PC-Stopp und Timer stoppen auch den Spielmodus.
- Fokuswechsel verwirft die vorbereitete Aktion; gehaltene Tasten werden losgelassen.
- Nur `GenshinImpact.exe` und `YuanShen.exe` sind erlaubt, keine Titel-Aehnlichkeit.
- Ein lokaler Lauf sendet Bilder nur an Ollama auf 127.0.0.1. Keine Bilder werden gespeichert.
- Drei ungueltige Modellantworten beenden den Lauf; eine einzelne fuehrt zu einem neuen Bild.
- Modellentscheidungen aelter als 20 Sekunden werden im Steuerungsmodus verworfen.
- Bei Menues/Unsicherheit stoppen; keine unbeaufsichtigten Kauf- oder Login-Aktionen.

Das Modell kann Wege, Feinde und Dialoge falsch erkennen. Teamnamen an der rechten
Seite gelten ausdruecklich nicht als Gegner. Zuverlaessiger Questabschluss ist noch
nicht nachgewiesen. Die Eingabefunktionen pruefen den Rueckgabewert von SendInput.

Protokolle: `src/genshin_agent/logs/`. Quellcode und Tests enthalten keine Zugangsdaten.
Der bestehende Spiele-Coach und das Freigabe-Gate fuer allgemeine PC-Aktionen bleiben
getrennte Funktionen. Kein automatischer Start beim Windows-Login.

Technische Referenzen:
- https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput
- https://docs.ollama.com/capabilities/structured-outputs
