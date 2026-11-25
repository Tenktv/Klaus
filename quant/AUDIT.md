# Audit des bestehenden Handelscodes (Phase 1)

Untersucht: `src/strategien.py`, `src/alpaca_handel.py`, `src/cfd_demo.py`, `src/markt.py`, `src/analysen.py`, `src/watchlist.py`, `tests/test_strategien.py`.

## Was es gibt
- **Live-Papierhandel** (`strategien.py`): Strategien `trend`, `rsi`, `sparplan` laufen alle 5 Minuten auf dem Server und senden Orders an das Alpaca-**Papier**-Konto
  (Echtgeld nur mit `ALPACA_LIVE=1` und immer mit Telegram-Knopf + PIN). Das bleibt unverändert und wird vom neuen Paket **nicht** berührt.
- **Alpaca-Anbindung** (`alpaca_handel.py`), **CFD-Demo** (`cfd_demo.py`), Marktdaten/Indikatoren über die inoffizielle Yahoo-Chart-API (`markt.py`), Analysen/Scanner.

## Befunde zum bisherigen Backtest (`strategien.backtest`)
| # | Befund | Auswirkung |
|---|--------|-----------|
| 1 | Ausführung zum **Schlusskurs des Folgetags**, nicht zum Open der nächsten Kerze | Modellannahme weicht von der gewünschten Regel ab (kein Look-ahead, aber unrealistisch zum Close) |
| 2 | **Keine Gebühren, keine Slippage** | Rendite zu optimistisch, besonders bei vielen Trades |
| 3 | **Keine Dividenden, keine Splits** als Ereignisse; Kurse stammen aus der Yahoo-Chart-API ohne Trennung roh/adjustiert | Ergebnisse nicht prüfbar; Dividenden fehlen komplett |
| 4 | **Ein Symbol, eine Position**, kein Portfolio, kein gemeinsamer Cash | Keine Multi-Asset-Aussagen möglich |
| 5 | Kein Risk Manager im Backtest (Limits nur im Live-Loop über `.env`) | Backtest und Live verhalten sich unterschiedlich |
| 6 | Kennzahlen: nur Rendite, Max-Verlust, Trefferquote; **kein Sharpe/Sortino/Profit Factor/Exposure**; `trades` zählt Käufe+Verkäufe, Trefferquote nur je Verkauf | Wenig belastbar |
| 7 | Keine Datenvalidierung (Duplikate, Lücken, NaN-Handling nur durch Weglassen von `None`-Schlusskursen) | Stille Fehler möglich |
| 8 | Keine zeitliche Validierung (Training/Test, Walk-Forward) | Overfitting nicht erkennbar |
| 9 | Abhängigkeiten `numpy`/`pandas` fehlten in `requirements.txt` (numpy wurde bereits importiert) | Installation auf frischem System bricht |

## Technische Schulden
- `markt._verlauf` hat keinen Cache und keine Fehlerklassen; Yahoo ist eine inoffizielle Quelle (kann jederzeit abweichen/ausfallen).
- Tests für die Live-Schleife existieren (`tests/test_strategien.py`), aber keine mit bekannten Handrechnungen für den Backtest.

## Umsetzung
Das neue Paket `quant/` ersetzt den alten Backtest **nicht** (Live-Betrieb bleibt stabil), sondern liefert einen korrekten, getesteten Kern daneben.
Migration des Live-Pfads auf `quant/` ist ein späterer, getrennter Schritt (siehe README, „Offene Aufgaben“).
