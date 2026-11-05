# Kalorien-App

Fitness- und Kalorien-Tagebuch für das iPhone – **läuft komplett ohne Klaus** (eigener Server, eigene Datenbank) und
lässt sich per Schnittstelle mit Klaus, Telegram oder Kurzbefehlen verbinden.

| Funktion | Stand |
|---|---|
| Foto machen → KI schätzt Gerichte, Menge, Kalorien, Eiweiß/Kohlenhydrate/Fett (Werte vor dem Eintragen änderbar) | ✅ |
| Beschreiben („2 Scheiben Vollkornbrot mit …“) → detaillierte Schätzung | ✅ |
| Barcode scannen (Kamera) oder Nummer tippen → Open Food Facts, Menge in Gramm | ✅ |
| Von Hand eintragen, Mahlzeiten, Tagesring, 7-Tage-Übersicht, Tagesziele (auch berechnet) | ✅ |
| Forum (Beiträge, Antworten) und Community-Chat | ✅ |
| Melden, Blockieren, Löschen, Moderator-Liste, Textfilter, Sende-Bremsen | ✅ |
| Konto löschen + Daten exportieren (DSGVO) | ✅ |
| Schnittstelle: Zugangs-Schlüssel (`kt_…`) → Klaus/Telegram: `/kalorien`, `/essen …`, Foto mit „Essen“ | ✅ |
| **Fitness-Social-Media:** Feed mit Fotos (Standort im Foto wird entfernt), Likes, Kommentare, „Folge ich“-Feed, Profile mit Über-mich, Folgen, Leute suchen | ✅ |
| Training eintragen (Kalorien automatisch aus Sportart, Dauer und Gewicht geschätzt), im Feed teilen | ✅ |
| Wasser, Gewichtsverlauf, Serien (🔥 Tage in Folge), Abzeichen, Wochen-Rangliste (freiwillig, pro Tag max. 240 Min.) | ✅ |
| Foto-Beiträge ohne KI-Prüfung: Melden/Löschen/Blockieren statt automatischer Bilderkennung | ⚠️ siehe Moderation |
| **Klesro Fit (neues Design „Startnummer“):** Workout-Tracker (Sätze, Pausen-Timer, Rekorde per Epley-1RM, Routinen, Statistik) | ✅ |
| **Reels:** Kurzvideos bis 60 s hochladen, ffmpeg wandelt zu H.264/AAC (≤720p, Metadaten entfernt), Vollbild-Feed mit Autoplay, Likes, Kommentare | ✅ |
| **Rezepte:** 10 Start-Rezepte, Portionen skalieren, ins Tagebuch, speichern, eigene anlegen, KI-Rezeptentwurf (Pro) | ✅ |
| **Pro-Plan:** per Code (Admin erstellt sie, Einlösen in „Ich“), eigene KI mit eigenem API-Schlüssel (Gemini/OpenAI/Anthropic/Groq/OpenRouter), KI-Coach; Schlüssel nur serverseitig, nie zurückgegeben | ✅ |
| Direktnachrichten, Gruppen/Challenges, Push-Nachrichten, echte Bezahlung (Stripe), App-Store-Paket | ⏳ noch nicht |

## Starten (Server oder PC)

```bash
cd Klaus
python -m kalorien.server          # http://127.0.0.1:7730 – nur Python-Standardbibliothek
```

Einstellungen in der `.env` (alle optional außer dem KI-Schlüssel für Foto/Text):

```
GEMINI_API_KEY=...          # Foto- und Text-Schätzung; ohne ihn gehen Tagebuch, Barcode, Forum, Chat trotzdem
KALORIEN_ADMINS=Nikola      # Namen mit Moderationsrechten (Beiträge löschen, Meldungen lesen, sperren)
KALORIEN_KI_PRO_TAG=30      # KI-Schätzungen pro Nutzer und Tag (schützt dein Gemini-Guthaben)
KALORIEN_PROXY=1            # nur wenn Caddy davorsteht
KALORIEN_OFFEN=0            # 0 = Registrierung geschlossen
KALORIEN_KI_PRO_TAG ist das Limit der kostenlosen Version; Pro hat eigene Grenzen (pro.py)
# Reels brauchen ffmpeg auf dem Server (apt install ffmpeg); Caddy: Upload-Limit für /api/reel erhöhen
```

Dauerhaft auf dem Server: `server/kalorien.service` (systemd, siehe Kommentar dort).

## Aufs iPhone

1. Die App braucht **HTTPS** (Kamera-Scanner!). Mit Caddy und einer Domain: `kalorien.deine-domain.de { reverse_proxy 127.0.0.1:7730 }`
2. In **Safari** die Adresse öffnen → Teilen → **Zum Home-Bildschirm**. Danach startet sie wie eine App (Vollbild, Icon, offline-Hülle).
3. Konto erstellen, unter **Ich** Ziele berechnen lassen.

Das ist eine Web-App (PWA), kein App-Store-Paket. Für den App Store wäre sie in Capacitor zu verpacken – dafür braucht es einen Mac,
das Apple-Entwicklerkonto (99 €/Jahr) und die Pflichtfunktionen, die schon drin sind (Konto löschen, Melden, Blockieren).

## Mit Klaus verbinden (Telegram)

1. In der App: **Ich → Schnittstelle** → Name „Klaus“ → *Schlüssel erstellen* → kopieren (wird nur einmal angezeigt).
2. In Klaus: **Einstellungen → Kalorien-App**: Adresse + Schlüssel eintragen.
3. Telegram: `/kalorien` (Tageswerte) · `/essen 2 Eier mit Toast` · `/essen_weg` (zurücknehmen) · Foto senden mit Beschriftung `Essen`.

Wer die App **ohne** Klaus kauft, nutzt dieselbe Schnittstelle (`Authorization: Bearer kt_…`) – z. B. mit einem iPhone-Kurzbefehl
oder einem eigenen Bot. Endpunkte: `GET /api/tag?datum=`, `POST /api/eintrag`, `POST /api/schaetzen/text|bild`, `GET /api/barcode/<nr>`,
`GET /api/woche`, `GET /api/export`.

## Datenschutz & Recht (bitte vor dem Verkauf klären)

- **Gesundheitsdaten** (Essen, Gewicht, Ziele) sind besondere Kategorien nach Art. 9 DSGVO → Einwilligung (ist als Pflicht-Haken bei der
  Registrierung drin), Datenschutzerklärung, Verzeichnis der Verarbeitungstätigkeiten, ggf. Auftragsverarbeitung mit dem Hoster.
- **Fotos** gehen an Google (Gemini) und werden von der App **nicht gespeichert**. Das muss in der Datenschutzerklärung stehen;
  für Gemini ist das bezahlte API-Konto vorzuziehen (dort werden Eingaben nicht zum Training genutzt – Bedingungen selbst prüfen).
- **Feed-Fotos** liegen auf dem Server (`data/kalorien_bilder/`), sind für alle angemeldeten Mitglieder sichtbar und werden beim Löschen des
  Beitrags oder Kontos gelöscht. EXIF/GPS wird serverseitig entfernt. Es gibt keine automatische Bilderprüfung: rechne mit Meldungen
  (Nacktheit, Körperbilder, Essstörungs-Inhalte) und plane jemanden ein, der `/api/meldungen` liest – für den App Store ist Moderation Pflicht.
- **Rangliste/Profile** zeigen nur Name, Bio, Serie, Trainingsminuten; das Tagebuch (Essen, Gewicht, Wasser) bleibt immer privat.
- **Forum/Chat** = Nutzerinhalte: Impressum, Nutzungsregeln, Melde- und Löschweg (drin), jemand muss Meldungen lesen (`/api/meldungen` als Admin).
- Passwörter werden mit scrypt gehasht, Schlüssel nur als SHA-256 gespeichert. Kein Tracking, keine Werbe-SDKs.
- Kalorienwerte sind **Schätzungen**, keine medizinische Beratung (Hinweis steht in der App). Keine Crash-Diäten empfehlen.
- Kein Mindestalter-Check außer Haken (16). Für Minderjährige und Essstörungs-Themen ist ein Moderationskonzept sinnvoll.

## KI-Reihenfolge auf dem Server

Foto-/Text-Schätzung fragen zuerst Gemini (`KALORIEN_MODELL`). Bei Überlastung (5xx) wird einmal wiederholt, danach das Ersatzmodell
(`KALORIEN_MODELL_ERSATZ`) probiert; ist das Kontingent leer (429) oder das Modell weg (404), geht es gleich dort weiter. Hilft das nicht und
steht `GROQ_API_KEY` in der `.env` (gratis: console.groq.com/keys), antwortet **Groq** (`KALORIEN_GROQ_MODELL`, Standard Llama 4 Scout mit Bildern).
Fehlt der Gemini-Schlüssel ganz, läuft alles über Groq. Falsche Schlüssel (401/403) werden nie umgangen. Die eigene KI eines Nutzers nutzt
nie die Server-Schlüssel.
