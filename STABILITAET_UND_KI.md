# Klaus - Stabilitaet und Premium-Textmodelle

## Ruhe und Herkunft

Im Kontrollzentrum schaltet **Ruhemodus** alle gesprochenen Antworten aus. Mikrofon/Verarbeitung bleiben separat
steuerbar; Textantworten erscheinen weiterhin. Kalender- und automatische Protokoll-Abschlussmeldungen sprechen
standardmaessig auch ausserhalb des Ruhemodus nicht. Explizit gestarteter Coach kann ausserhalb des Ruhemodus sprechen.
Die letzte Sprachausgabe zeigt Quelle und Zeitpunkt; diese Daten enthalten keinen Antworttext.
Gemini-Audio wird in unterbrechbare 100-ms-Stuecke geteilt. Der nicht zuverlaessig unterbrechbare Windows-TTS-Fallback
ist deaktiviert; scheitern die gewaehlte Stimme und Piper, bleibt die Antwort als Text.
Telegram: `/ruhe`, `/ruhe an`, `/ruhe aus`. Der PC muss erreichbar sein. Ruhemodus persistiert lokal in `data/betrieb.json`.

Desktop und alter Voice-Starter teilen sich eine Windows-Prozesssperre. Zwei pythonw-PIDs allein bedeuten keine zwei
Assistenten: eine venv kann einen Launcher plus Arbeitsprozess haben. Entscheidend ist die gemeinsame Sperre.

## Protokoll-Waechter

Warnungen bei mehr als zehn Minuten ohne Text (kann eine Pause sein), fehlenden Audiodaten, zwei Minuten ohne
Mitschrift-Worker-Fortschritt, beendetem Worker, Transkriptionsfehler, ueberfuelltem Audio-Puffer oder ausgefallenem PC-Ton.
Identische Warnungen werden nicht wiederholt; Erholung wird gemeldet. Meldungen kommen als Text im Panel/Telegram,
nicht als neue TTS-Ansage. Audio-Puffer ist begrenzt; verlorene Daten werden kenntlich gemacht.
Laufende Markdown-Notizen werden ueber eine temporaere Datei atomisch ersetzt.

## Premium vorbereiten

**Premium bleibt standardmaessig aus.** Keine neuen API-Schluessel wurden eingetragen, keine bezahlten Tests ausgefuehrt.

1. `ki_modelle.beispiel.json` nach `data/ki_modelle.json` kopieren.
2. Exakte Modell-ID, Anbietername, aktuelle konservative Eingabe-/Ausgabepreise pro Million Token und Ausgabegrenze
   eintragen. Null/ungueltige Preise und nicht konfigurierte Modelle werden abgelehnt.
3. Tages- und Monatslimit in USD setzen. Erst dann bewusst `aktiv: true` setzen.
4. Schluessel bleiben in `.env`: OpenRouter oder `OPENAI_API_KEY`. Eigene OpenAI-kompatible Dienste nutzen die bestehenden
   `ERSATZ_KI_URL`, `ERSATZ_KI_KEY`, `ERSATZ_KI_MODELLE`. Keine Schluessel in die Modell-JSON schreiben.

Anbieternamen: `openrouter1`, `openrouter2`, `openai`, `eigen`, optional `groq`. Konfigurierte Premium-Anbieter/Modelle
werden bevorzugt; ohne Freigabe bleibt die Gratis-Reihenfolge. OpenRouter waehlt nie ungefragt ein kostenpflichtiges
Modell aus dem Katalog. `.env`/Konfiguration sind pro Installation, nicht ein gemeinsames Kundenkonto.

Vor jedem bezahlten **Text**-Aufruf wird anhand der Text-Bytes, Werkzeuge, Preise und begrenzten Ausgabe eine konservative
Summe in SQLite reserviert. Transaktionen verhindern parallele Ueberbuchung. Gemeldete `usage.cost` wird verbucht,
sonst wird Token-Nutzung mit konfigurierten Preisen geschaetzt. Fehlt Nutzung/antwortet der Anbieter nicht, bleibt die
volle Reservierung erhalten. Die Datenbank speichert Anbieter, Modell, Betrag und Buchungszustand, keine Prompts/Schluessel.
`/ki` und das Kontrollzentrum zeigen Summen **inklusive Reservierungen**, keinen Anbieter-Rechnungsstand.

Grenzen: Dies ist kein garantierter Rechnungsdeckel. Tarifwechsel, Nebenkosten und andere Clients koennen ausserhalb
dieser Rechnung liegen. Zusaetzlich beim Anbieter ein Kreditlimit setzen. PC und Server fuehren getrennte lokale
Kostenrahmen; dieselben Kontoschluessel teilen weiterhin das Anbieter-Guthaben.

Dieser Kostenrahmen deckt die konfigurierten Premium-Textmodelle der Ersatz-KI ab. Gemini Live, direkte Gemini-Aufrufe,
Fish/TTS, Bild-/Video-Generierung und andere Dienste sind noch nicht darin budgetiert. Kostenpflichtige Bildaufrufe
ueber diese neue Premium-Route werden abgelehnt. Vor einem Verkauf brauchen diese Wege ebenfalls eigene Limits bzw.
Abrechnung, einen Setup-Assistenten und eine zentrale Kundenkostenverwaltung. Klaus ist damit noch kein fertiges Produkt.

## Pruefung

`.venv\Scripts\python.exe -m unittest discover -s tests`

Die Tests verwenden temporare Dateien, simulierte API-Antworten/Audioausgabe und eine reine Windows-Mutex-Pruefung in
einem zweiten Python-Prozess. Keine Aufnahme, echte Klicks, bezahlte Generierung oder Klaus-App-Starts.
