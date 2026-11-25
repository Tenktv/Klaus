# Klaus Quant – Backtesting-Kern & Paper-Broker (Version 0.2)

Modularer, deterministischer **Long-only-Backtest** für Aktien und ETFs auf Tagesdaten. **Reine Simulation: das Paket löst keine echten Orders aus,
enthält keinen Broker-Code, keine Schlüssel und kein Netzwerk außer dem optionalen Yahoo-Datenadapter.** Keine Anlageberatung; Ergebnisse auf
künstlichen Daten sagen nichts über reale Märkte. Ausgangslage und Befunde: [`AUDIT.md`](AUDIT.md).

## Status (ehrlich)
| Bereich | Status |
|---|---|
| Datenvalidierung (Duplikate, NaN, Lücken, ungültige Kerzen, Zeitzonen) | Implementiert, getestet |
| Adapter CSV / JSON / DataFrame, lokaler Cache | Implementiert, getestet |
| Adapter Yahoo Finance (`yfinance`) | Teilweise: mit gespieltem `yfinance` getestet; **gegen die echte API NICHT VERIFIZIERT** (in der Entwicklungsumgebung blockiert: `python -m quant.verify_data` meldet `not_verified`) |
| Datenprüfung `data_check.py` (Vollständigkeit, Kalender, Ausreißer, Adjusted Close, Dividenden, Splits, Quellenabgleich) | Implementiert, getestet (auf künstlichen Daten); echte Daten stehen aus |
| Börsenkalender (NYSE, NASDAQ, XETRA, LSE, TSE, Krypto 24/7; Feiertage, verkürzte Tage, Handelszeiten) via `exchange_calendars` | Implementiert, getestet |
| Paper-Broker (Market/Limit/Stop, Gebühren, Slippage, Cash, Risk Manager, Journal, atomares Speichern, Wiederherstellung) | Implementiert, getestet (gleiches Ergebnis wie der Backtest) |
| Portfolio (mehrere Positionen, Cash, Gebühren, Slippage, realisiert/unrealisiert) | Implementiert, getestet |
| Backtest-Engine (Next-Open, mehrere Symbole, unterschiedliche Kalender, Benchmark) | Implementiert, getestet (Handrechnung 5 Tage) |
| Dividenden & Splits als Ereignisse | Implementiert, getestet |
| Risk Manager (Positionsgröße, Cash-Reserve, Exposure, Risiko je Position, Drawdown-Stopp, max. Positionen) | Implementiert, getestet |
| Metrics (Rendite, Risiko, Trade-Statistik, Exposure) | Implementiert, getestet |
| Strategien EMA 20/50, RSI-14 + Trendfilter | Implementiert, getestet |
| Strategien MACD, Momentum, Mean Reversion | **Noch nicht implementiert** |
| Walk-Forward / Train-Validation-OOS-Aufteilung | Implementiert, getestet (Parameterwahl nur aus Trainingsdaten) |
| Märkte Krypto / Forex | Nur vorbereitet (`MARKETS`, **gesperrt**, `enabled=False`) |
| AI Engine (Regime, ML-Baselines) | **Noch nicht implementiert** |
| Dashboard (Streamlit) | **Noch nicht implementiert** |

## Installation
```bash
pip install -r requirements.txt          # numpy, pandas>=2.2 (Pflicht); yfinance nur für den Yahoo-Adapter
python -m unittest discover -s tests -p "test_quant*.py"
python -m quant.example                  # Demo auf künstlichen Daten
```

## Architektur
```
quant/
  config.py              BacktestConfig, RiskConfig, MarketConfig (+ MARKETS: equity, etf aktiv; crypto, forex gesperrt)
  data.py                validate_ohlcv, load_csv/load_json/from_dataframe, CsvDirSource, YahooSource, CachedSource
  corporate_actions.py   Dividenden und Splits
  portfolio.py           Order, Position, Trade, Portfolio
  risk.py                RiskManager (unabhängig von Strategie/KI, kann nur begrenzen/ablehnen)
  metrics.py             Kennzahlen inkl. dokumentierter Definitionen
  backtest.py            BacktestEngine (event-basiert, deterministisch)
  strategies/            Strategy (Basis), EmaCrossStrategy, RsiTrendStrategy
  validation.py          time_split, walk_forward_windows, walk_forward
  execution.py           GEMEINSAME Kosten-, Sizing-, Risiko- und Buchungslogik (Backtest UND Paper-Broker)
  calendar.py            MarketCalendar (exchange_calendars)
  paper.py               PaperBroker, PaperTrader (virtuelle Orders; kein Netzwerk, kein Live-Broker-Code)
  data_check.py          check_prices, compare_frames, verify_source ("not_verified" statt erfundener Ergebnisse)
  verify_data.py         CLI: python -m quant.verify_data AAPL SPY --start ... --end ...
tests/test_quant_*.py    121 Tests (unittest)
```

## Backtest-Regeln (Modellannahmen – keine Garantie für reale Ausführung)
1. Signale entstehen **nur nach Abschluss einer Kerze** aus der Historie bis einschließlich dieser Kerze (die Engine übergibt nie mehr; ein Assert prüft das).
2. Ausführung **frühestens zum Open der nächsten verfügbaren Kerze** des Symbols (rohe OHLC-Preise). Das ist eine Modellannahme.
3. Slippage auf den Fillpreis (Kauf teurer, Verkauf billiger; Standard 0,02 %), Gebühr je Orderseite auf das Volumen (Standard 0,01 %). Alles konfigurierbar.
4. Reihenfolge je Handelstag: Corporate Actions → Verkäufe → Käufe (alphabetisch) → Bewertung zum Schluss → neue Signale.
5. Cash: Käufe/Gebühren senken, Verkäufe erhöhen Cash; nie negativ, keine Leerverkäufe. Signale der letzten Kerze verfallen (`expired`).
6. **Dividenden** als Cash am Ex-Tag für Stücke, die am Vorabend gehalten wurden; **Splits** passen Stück und Einstand an. **Adjusted Close wird nie zur
   Ausführung benutzt**, Dividenden werden nie doppelt gebucht (Details in `corporate_actions.py`).
7. Sizing: Zielgewicht `position_size_pct` vom Gesamtwert, ganze Stücke; der Risk Manager begrenzt vorab und prüft die Order danach endgültig (Ablehnung mit Begründung).

## Benutzung
```python
from quant.backtest import BacktestEngine
from quant.config import BacktestConfig, RiskConfig
from quant.data import load_csv
from quant.strategies import EmaCrossStrategy

aapl, report = load_csv("AAPL.csv", "AAPL")            # Spalten: Date, Open, High, Low, Close[, Adj Close][, Volume]
engine = BacktestEngine({"AAPL": aapl}, EmaCrossStrategy(20, 50),
                        BacktestConfig(initial_cash=100_000, fee_rate=0.0001, slippage_rate=0.0002),
                        risk=RiskConfig.beispiel_test())   # 10 % / 20 % Cash / 80 % - nur Testwerte
r = engine.run()
print(r.metrics); print(r.trades_frame()); print(r.equity_curve.tail())
```
Datenquelle immer dokumentieren (`MarketData.source`). Yahoo ist eine **inoffizielle** Quelle; deren „rohe“ Kurse sind bereits split-, aber nicht
dividendenbereinigt (`prices_split_adjusted=True`).

## Paper-Broker (Phase 6)
```python
from quant.paper import PaperBroker, PaperTrader
from quant.calendar import MarketCalendar
b = PaperBroker(BacktestConfig(initial_cash=10_000), RiskConfig.beispiel_test(), calendar=MarketCalendar("NYSE"),
                state_path="data/quant_paper.json", journal_path="data/quant_paper_journal.jsonl")
b.submit("AAPL", "buy", 10, "limit", limit_price=180.0)                 # market | limit | stop; time_in_force day | gtc
b.process_day("2024-11-29", {"AAPL": {"open": 181, "high": 183, "low": 179.5, "close": 182, "volume": 1e6}})
b = PaperBroker.load("data/quant_paper.json", calendar=MarketCalendar("NYSE"))     # nach Neustart
```
Fill-Regeln (Tageskerzen, Modellannahmen): Market = Open ± Slippage. Limit-Kauf: Open ≤ Limit → Open (höchstens Limit); sonst Tief **unter** dem Limit → Limit; sonst
**nicht ausgeführt** (bloße Berührung reicht standardmäßig nicht). Stop-Verkauf: Open ≤ Stop → Open − Slippage (Gap); sonst Tief ≤ Stop → Stop − Slippage. Orders wirken
frühestens auf der nächsten Kerze. Ungültige Kerzen, Feiertage und doppelte Lieferungen werden verworfen und im Journal protokolliert (`broker.errors`);
bei veralteten Daten (`stale_sessions`) werden keine neuen Käufe angenommen. Der Zustand wird nach jedem Tag atomar gespeichert (`.tmp` → `.bak` → Ersetzen),
beim Laden geprüft (Version, Cash ≥ 0, Equity-Identität) und bei kaputter Hauptdatei aus `.bak` wiederhergestellt. `PaperTrader` führt eine Strategie mit denselben
Regeln wie der Backtest aus (per Test: identische Equity-Kurve und Fills). Es gibt **keine** Verbindung zu den Live-Broker-Modulen in `src/` (per Test abgesichert).

## Datenquelle prüfen
`python -m quant.verify_data AAPL SPY --start 2020-01-01 --end 2024-12-31 --calendar NYSE` – ohne Netzwerk lautet das Ergebnis `not_verified` (Exit-Code 2).
„ok“ heißt nur: interne Konsistenz (Kalender, Ausreißer, Adjusted Close, Dividenden/Splits); für Übereinstimmung mit der Wirklichkeit `compare_frames` mit einer
zweiten, unabhängigen Quelle nutzen.

## Validierung gegen Overfitting
`time_split` (chronologisch Training/Validation/OOS) und `walk_forward` (Parameter nur aus dem Training wählen, Testfenster genau einmal fahren,
jede Periode einzeln ausgeben inkl. verwendeter Datenbereiche). Die finale Testperiode darf nicht zur Optimierung dienen.

## Bekannte Einschränkungen
- Paper-Fills auf Tageskerzen sind eine Näherung (keine Teilfüllungen, kein Orderbuch, Limit-Fill nur bei Durchhandeln).
- Tagesdaten, Long-only, keine Margin/Hebel/Shorts, kein Intraday, kein Orderbuch/Teilfüllungen, Fill zum Open immer möglich.
- Außerplanmäßige Börsenschließungen nur, soweit `exchange_calendars` sie kennt; Dividenden-Zahltag nicht modelliert; Steuern, Währungsumrechnung und Spreads fehlen.
- Benchmark = Kaufen+Halten des Roh-Schlusskurses ohne Kosten und Dividenden.
- Sharpe/Sortino sind bei wenigen Beobachtungen sehr unsicher; `None` heißt „undefiniert“, nicht 0.

## Offene Aufgaben (Reihenfolge)
1. Yahoo-Adapter und `verify_data` gegen die echte API laufen lassen (Netzwerk nötig), mit zweiter Quelle abgleichen.
2. Strategien MACD, Momentum, Mean Reversion (gleiche Basisklasse, gleiche Look-ahead-Tests).
3. Paper-Trader als dauerhaften Dienst (Scheduler, tägliche Datenlieferung, Telegram-Bericht) – bewusst noch nicht angebunden.
4. AI Engine: Features, Regimeerkennung, scikit-learn-Baselines mit Walk-Forward-Vergleich gegen die Regelstrategie.
5. Streamlit-Dashboard (nur echte, aus Läufen gespeicherte Daten).
6. Krypto/Forex nach eigener Validierung freischalten.
