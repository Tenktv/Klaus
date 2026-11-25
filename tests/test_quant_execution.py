"""Ausfuehrung: Kauf/Verkauf, Gebuehren, Slippage, Next-Open, Look-ahead, Equity-Kurve, mehrere Positionen, Kalender, Determinismus.
Der Fuenf-Tage-Datensatz ist von Hand gerechnet (Rechenweg im Kommentar)."""
import unittest

import pandas as pd

from tests._quant_helpers import Scripted, frame, random_walk
from quant.backtest import BacktestEngine
from quant.config import BacktestConfig, MARKETS
from quant.strategies import EmaCrossStrategy, RsiTrendStrategy

# Handrechnung (Startkapital 10.000, Gebuehr 0,1 %, Slippage 0,2 %, Zielgewicht 50 %, ganze Stuecke)
# Tag1..5 Open: 100,104,108,112,109 | Close: 102,106,110,111,108. Signal long auf Close Tag1, flach auf Close Tag3.
# Kauf Tag2 zum Open: 104 * 1,002 = 104,208. Ziel 5.000 -> 5.000 / (104,208 * 1,001) = 47,93 -> 47 Stueck.
#   Kosten 47*104,208 = 4.897,776 + Gebuehr 4,897776 -> Cash 5.097,326224
# Equity Tag2 (Close 106) = 5.097,326224 + 47*106 = 10.079,326224 ; Tag3 (110) = 10.267,326224
# Verkauf Tag4 zum Open: 112 * 0,998 = 111,776 ; Erloes 47*111,776 = 5.253,472 - Gebuehr 5,253472 -> Cash 10.345,544752
# P/L netto = (111,776-104,208)*47 - 5,253472 - 4,897776 = 345,544752 ; Gebuehren gesamt 10,151248
CFG = BacktestConfig(initial_cash=10_000, fee_rate=0.001, slippage_rate=0.002, position_size_pct=0.5)
FUENF = frame([100, 104, 108, 112, 109], [102, 106, 110, 111, 108], start="2024-01-01")   # Mo-Fr
SKRIPT = {"2024-01-01": 1, "2024-01-03": 0}


def lauf(cfg=CFG, data=None, script=None, **kw):
    return BacktestEngine({"AAA": FUENF if data is None else data}, Scripted(SKRIPT if script is None else script), cfg, **kw).run()


class TestFuenfTage(unittest.TestCase):
    def setUp(self):
        self.r = lauf()

    def test_kauf_wird_zum_naechsten_open_mit_slippage_und_gebuehr_ausgefuehrt(self):
        kauf = self.r.orders[0]
        self.assertEqual((kauf.side, str(kauf.signal_date), str(kauf.exec_date), kauf.status), ("buy", "2024-01-01", "2024-01-02", "filled"))
        self.assertEqual(kauf.ref_open, 104.0)
        self.assertAlmostEqual(kauf.exec_price, 104.208, places=9)          # Slippage 0,2 % auf den Open
        self.assertEqual(kauf.quantity, 47)
        self.assertAlmostEqual(kauf.fee, 4.897776, places=9)                # 0,1 % von 47 * 104,208
        self.assertAlmostEqual(kauf.slippage_cost, 47 * 0.208, places=9)

    def test_verkauf_profitabler_trade_und_alle_kontostaende(self):
        verkauf = self.r.orders[1]
        self.assertEqual((verkauf.side, str(verkauf.signal_date), str(verkauf.exec_date)), ("sell", "2024-01-03", "2024-01-04"))
        self.assertAlmostEqual(verkauf.exec_price, 111.776, places=9)
        self.assertAlmostEqual(verkauf.fee, 5.253472, places=9)
        t = self.r.trades[0]
        self.assertAlmostEqual(t.pnl, 345.544752, places=6)
        self.assertAlmostEqual(t.fees, 10.151248, places=6)
        pf = self.r.portfolio
        self.assertAlmostEqual(pf.cash, 10345.544752, places=6)
        self.assertEqual(pf.positions, {})
        self.assertAlmostEqual(pf.fees_total, 10.151248, places=6)
        self.assertAlmostEqual(pf.realized_pnl, 345.544752, places=6)

    def test_equity_kurve_tag_fuer_tag(self):
        e = self.r.equity_curve["equity"].tolist()
        erwartet = [10000.0, 10079.326224, 10267.326224, 10345.544752, 10345.544752]
        for a, b in zip(e, erwartet):
            self.assertAlmostEqual(a, b, places=6)
        self.assertAlmostEqual(self.r.equity_curve["cash"].iloc[1], 5097.326224, places=6)
        self.assertAlmostEqual(self.r.equity_curve["invested"].iloc[1], 4982.0, places=6)

    def test_kennzahlen_gegen_handrechnung(self):
        m = self.r.metrics
        self.assertAlmostEqual(m["net_return"], 0.0345544752, places=9)
        self.assertAlmostEqual(m["total_return"], (10345.544752 + 10.151248) / 10000 - 1, places=9)   # vor Gebuehren
        self.assertEqual((m["number_of_trades"], m["winning_trades"], m["losing_trades"]), (1, 1, 0))
        self.assertEqual(m["win_rate"], 1.0)
        self.assertIsNone(m["profit_factor"])            # keine Verluste -> undefiniert
        self.assertAlmostEqual(m["max_drawdown"], 0.0, places=12)
        self.assertEqual(m["average_holding_days"], 2)

    def test_buchhaltungsidentitaet(self):
        pf = self.r.portfolio
        self.assertAlmostEqual(pf.equity(), pf.initial_cash + pf.realized_pnl + pf.unrealized_pnl + pf.dividends_total, places=9)

    def test_deterministisch_zwei_laeufe_gleich(self):
        pd.testing.assert_frame_equal(self.r.equity_curve, lauf().equity_curve)
        self.assertEqual([(o.side, o.exec_price, o.quantity) for o in self.r.orders], [(o.side, o.exec_price, o.quantity) for o in lauf().orders])


class TestZeitpunkt(unittest.TestCase):
    def test_signal_an_tag_t_wird_fruehestens_an_t_plus_1_ausgefuehrt(self):
        r = lauf()
        for o in r.orders:
            if o.status == "filled":
                self.assertGreater(o.exec_date, o.signal_date)

    def test_fill_nutzt_open_der_folgekerze_nicht_den_signalschluss(self):
        # Tag 2 Open weicht stark vom Schluss des Signaltags ab: der Fill muss exakt dem Open entsprechen
        d = frame([100, 150, 150, 150], [100, 150, 150, 150])
        r = lauf(CFG, d, {"2024-01-01": 1})
        self.assertAlmostEqual(r.orders[0].exec_price, 150 * 1.002, places=9)

    def test_strategie_sieht_nie_kerzen_nach_dem_aktuellen_tag(self):
        e = BacktestEngine({"AAA": FUENF}, Scripted(SKRIPT), CFG)
        e.run()
        self.assertEqual(e.strategies["AAA"].seen_last, list(FUENF.index))        # je Kerze genau die Historie bis zu dieser Kerze

    def test_signal_der_letzten_kerze_wird_nicht_ausgefuehrt(self):
        r = lauf(CFG, FUENF, {"2024-01-05": 1})
        self.assertEqual(r.orders[0].status, "expired")
        self.assertEqual(r.portfolio.positions, {})

    def test_indikatoren_sind_kausal_abgeschnittene_historie_gibt_gleiches_signal(self):
        d = random_walk(260, seed=3)
        for strat in (EmaCrossStrategy(5, 20), RsiTrendStrategy(14, 40, 60, 50)):
            voll = strat.generate_signals(d)
            for t in range(60, 260, 17):
                kurz = strat.generate_signals(d.iloc[: t + 1])
                pd.testing.assert_series_equal(voll.iloc[: t + 1], kurz, check_names=False)

    def test_zukunft_zu_aendern_aendert_vergangene_signale_nicht(self):
        d = random_walk(200, seed=4)
        d2 = d.copy()
        d2.iloc[150:, d2.columns.get_indexer(["open", "high", "low", "close"])] *= 3
        for strat in (EmaCrossStrategy(5, 20), RsiTrendStrategy(14, 40, 60, 50)):
            pd.testing.assert_series_equal(strat.generate_signals(d).iloc[:150], strat.generate_signals(d2).iloc[:150], check_names=False)


class TestVerlustUndGrenzen(unittest.TestCase):
    def test_verlusttrade_reduziert_equity_und_cash(self):
        d = frame([100, 100, 90, 80, 80], [100, 95, 85, 80, 80])
        r = lauf(CFG, d, {"2024-01-01": 1, "2024-01-03": 0})
        t = r.trades[0]
        self.assertLess(t.pnl, 0)
        self.assertLess(r.portfolio.cash, 10_000)
        self.assertLess(r.equity_curve["equity"].iloc[-1], 10_000)
        # Kauf Tag2 Open 100*1,002=100,2 ; 49 Stueck (5000/(100,2*1,001)=49,85) ; Verkauf Tag4 Open 80*0,998=79,84
        self.assertEqual(r.orders[0].quantity, 49)
        erwartet = (79.84 - 100.2) * 49 - 49 * 79.84 * 0.001 - 49 * 100.2 * 0.001
        self.assertAlmostEqual(t.pnl, erwartet, places=6)
        self.assertEqual((r.metrics["losing_trades"], r.metrics["winning_trades"]), (1, 0))
        self.assertEqual(r.metrics["profit_factor"], 0.0)
        self.assertLess(r.metrics["max_drawdown"], 0)

    def test_kein_negatives_cash_und_keine_position_ohne_kapital(self):
        d = frame([1000, 1000, 1000], [1000, 1000, 1000])
        r = BacktestEngine({"A": d}, Scripted({"2024-01-01": 1}), BacktestConfig(initial_cash=500, position_size_pct=1.0)).run()
        self.assertEqual(r.orders[0].status, "rejected")           # 1 Stueck kostet 1.000 > 500
        self.assertEqual(r.portfolio.positions, {})
        self.assertGreaterEqual(r.portfolio.cash, 0)

    def test_keine_trades(self):
        r = lauf(CFG, FUENF, {})
        self.assertEqual(r.metrics["number_of_trades"], 0)
        self.assertIsNone(r.metrics["win_rate"])
        self.assertIsNone(r.metrics["profit_factor"])
        self.assertIsNone(r.metrics["average_holding_days"])
        self.assertEqual(r.metrics["net_return"], 0.0)
        self.assertEqual(r.equity_curve["equity"].tolist(), [10_000.0] * 5)

    def test_gebuehren_und_slippage_sind_veraenderbar_null_kosten(self):
        r = lauf(BacktestConfig(initial_cash=10_000, fee_rate=0, slippage_rate=0, position_size_pct=0.5))
        self.assertEqual(r.orders[0].exec_price, 104.0)
        self.assertEqual(r.portfolio.fees_total, 0)
        self.assertEqual(r.orders[0].quantity, 48)                  # 5000/104 = 48,07
        self.assertAlmostEqual(r.trades[0].pnl, 48 * (112 - 104), places=9)


class TestMehrereSymbole(unittest.TestCase):
    def test_mehrere_gleichzeitige_positionen(self):
        a = frame([100] * 6, [100] * 6)
        b = frame([50] * 6, [50] * 6)
        r = BacktestEngine({"AAA": a, "BBB": b}, Scripted({"2024-01-01": 1}), BacktestConfig(initial_cash=10_000, fee_rate=0, slippage_rate=0, position_size_pct=0.2)).run()
        self.assertEqual(sorted(r.portfolio.positions), ["AAA", "BBB"])
        self.assertEqual(r.portfolio.positions["AAA"].quantity, 20)       # 2000 / 100
        self.assertEqual(r.portfolio.positions["BBB"].quantity, 40)       # 2000 / 50
        self.assertEqual(r.equity_curve["open_positions"].iloc[-1], 2)
        self.assertAlmostEqual(r.portfolio.cash, 6000.0, places=9)

    def test_unterschiedliche_handelskalender(self):
        # BBB hat an Tag 3 (2024-01-03) keine Kerze (z. B. Feiertag). Signal fuer BBB am Tag 2 -> Ausfuehrung erst an Tag 4.
        a = frame([100] * 5, [100] * 5, start="2024-01-01")
        tage_b = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-04", "2024-01-05"])
        b = frame([50, 50, 60, 60], [50, 50, 60, 60], dates=tage_b)
        r = BacktestEngine({"AAA": a, "BBB": b}, {"BBB": Scripted({"2024-01-02": 1}), "AAA": Scripted({})},
                           BacktestConfig(initial_cash=10_000, fee_rate=0, slippage_rate=0, position_size_pct=0.5)).run()
        o = r.orders[0]
        self.assertEqual((str(o.signal_date), str(o.exec_date), o.exec_price), ("2024-01-02", "2024-01-04", 60.0))
        self.assertEqual(len(r.equity_curve), 5)                        # Vereinigung der Kalender
        # am 3. Januar wird BBB mit dem letzten bekannten Schluss (50) bewertet, nicht mit 0
        self.assertAlmostEqual(r.equity_curve["equity"].iloc[2], 10_000.0, places=9)
        self.assertEqual(r.signals[-1]["symbol"], "BBB")

    def test_equity_bewertet_offene_position_mit_dem_schlusskurs(self):
        d = frame([100, 100, 100, 100], [100, 110, 120, 130])
        r = BacktestEngine({"A": d}, Scripted({"2024-01-01": 1}), BacktestConfig(initial_cash=10_000, fee_rate=0, slippage_rate=0, position_size_pct=1.0)).run()
        self.assertEqual(r.portfolio.positions["A"].quantity, 100)
        self.assertEqual(r.equity_curve["equity"].tolist(), [10000.0, 11000.0, 12000.0, 13000.0])   # Kauf zum Open von Tag 2 (100), Schluesse 110/120/130
        self.assertAlmostEqual(r.metrics["unrealized_pnl"], 3000.0, places=9)

    def test_nicht_freigeschaltete_maerkte_werden_abgelehnt(self):
        with self.assertRaises(ValueError):
            BacktestEngine({"BTC": FUENF}, Scripted({}), CFG, symbol_markets={"BTC": "crypto"})
        self.assertFalse(MARKETS["crypto"].enabled)
        self.assertFalse(MARKETS["forex"].enabled)

    def test_benchmark_kaufen_und_halten(self):
        d = frame([100, 100, 100, 100], [100, 110, 120, 130])
        r = BacktestEngine({"A": d}, Scripted({}), BacktestConfig(initial_cash=10_000, benchmark="A")).run()
        self.assertAlmostEqual(r.metrics["benchmark_return"], 0.30, places=9)


if __name__ == "__main__":
    unittest.main()
