# Klaus Quant – Backtesting-Kern (Version 0.1)

Modularer, deterministischer **Long-only-Backtest** für Aktien und ETFs auf Tagesdaten. **Reine Simulation: das Paket löst keine echten Orders aus,
enthält keinen Broker-Code, keine Schlüssel und kein Netzwerk außer dem optionalen Yahoo-Datenadapter.** Keine Anlageberatung; Ergebnisse auf
künstlichen Daten sagen nichts über reale Märkte. Ausgangslage und Befunde: [`AUDIT.md`](AUDIT.md).

## Status (ehrlich)
| Bereich | Status |
|---|---|
| Datenvalidierung (Duplikate, NaN, Lücken, ungültige Kerzen, Zeitzonen) | Implementiert, getestet |
| Adapter CSV / JSON / DataFrame, lokaler Cache | Implementiert, getestet |
| Adapter Yahoo Finance (`yfinance`) | Teilweise: nur mit gespieltem `yfinance` getestet, **nicht gegen die echte API** |
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
| Paper-Trading-Broker (separat) | **Noch nicht implementiert** (der bestehende Live-Papierhandel in `src/strategien.py` läuft unabhängig weiter) |
| Dashboard (Streamlit) | **Noch nicht implementiert** |
| Börsenkalender mit Feiertagen | **Noch nicht implementiert** (nur Mo–Fr bzw. 24/7 + Lückenerkennung) |

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
tests/test_quant_*.py    75 Tests (unittest)
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

## Validierung gegen Overfitting
`time_split` (chronologisch Training/Validation/OOS) und `walk_forward` (Parameter nur aus dem Training wählen, Testfenster genau einmal fahren,
jede Periode einzeln ausgeben inkl. verwendeter Datenbereiche). Die finale Testperiode darf nicht zur Optimierung dienen.

## Bekannte Einschränkungen
- Tagesdaten, Long-only, keine Margin/Hebel/Shorts, kein Intraday, kein Orderbuch/Teilfüllungen, Fill zum Open immer möglich.
- Kein Feiertagskalender; Dividenden-Zahltag nicht modelliert; Steuern, Währungsumrechnung und Spreads fehlen.
- Benchmark = Kaufen+Halten des Roh-Schlusskurses ohne Kosten und Dividenden.
- Sharpe/Sortino sind bei wenigen Beobachtungen sehr unsicher; `None` heißt „undefiniert“, nicht 0.

## Offene Aufgaben (Reihenfolge)
1. Yahoo-Adapter gegen die echte API prüfen; Börsenkalender (`pandas_market_calendars`).
2. Strategien MACD, Momentum, Mean Reversion (gleiche Basisklasse, gleiche Look-ahead-Tests).
3. Separates Paper-Trading-Modul (virtueller Broker auf dieser Engine) und Anbindung des bestehenden Alpaca-Papierhandels.
4. AI Engine: Features, Regimeerkennung, scikit-learn-Baselines mit Walk-Forward-Vergleich gegen die Regelstrategie.
5. Streamlit-Dashboard (nur echte, aus Läufen gespeicherte Daten).
6. Krypto/Forex nach eigener Validierung freischalten.
