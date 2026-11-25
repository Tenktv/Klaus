"""Portfolio-Buchhaltung direkt (ohne Engine) + Risk Manager + Metrics mit bekannten Werten."""
import datetime as dt
import math
import unittest

import numpy as np
import pandas as pd

from tests._quant_helpers import Scripted, frame
from quant import metrics as M
from quant.backtest import BacktestEngine
from quant.config import BacktestConfig, RiskConfig
from quant.portfolio import InsufficientCash, Portfolio, PortfolioError, Trade
from quant.risk import RiskManager

D = dt.date(2024, 1, 2)


class TestPortfolio(unittest.TestCase):
    def test_kauf_verkauf_cash_und_pnl(self):
        pf = Portfolio(10_000)
        pf.buy("A", 10, 100.0, 1.0, D)                       # -1001
        self.assertAlmostEqual(pf.cash, 8999.0)
        pf.mark({"A": 110.0})
        self.assertAlmostEqual(pf.equity(), 8999.0 + 1100.0)
        self.assertAlmostEqual(pf.unrealized_pnl, 100.0 - 1.0)   # Kursgewinn minus Einstiegsgebuehr
        t = pf.sell("A", 10, 110.0, 1.1, D + dt.timedelta(days=3))
        self.assertAlmostEqual(pf.cash, 8999.0 + 1100.0 - 1.1)
        self.assertAlmostEqual(t.pnl, 100.0 - 1.1 - 1.0)
        self.assertEqual((t.holding_days, pf.positions), (3, {}))
        self.assertAlmostEqual(pf.equity(), 10_000 + 100 - 2.1)

    def test_teilverkauf_und_durchschnittlicher_einstand(self):
        pf = Portfolio(10_000)
        pf.buy("A", 10, 100.0, 0, D)
        pf.buy("A", 10, 120.0, 0, D)
        self.assertAlmostEqual(pf.positions["A"].avg_entry_price, 110.0)
        pf.sell("A", 5, 130.0, 0, D)
        self.assertEqual(pf.positions["A"].quantity, 15)
        self.assertAlmostEqual(pf.realized_pnl, 100.0)
        self.assertAlmostEqual(pf.positions["A"].avg_entry_price, 110.0)

    def test_kein_negatives_cash_und_keine_leerverkaeufe(self):
        pf = Portfolio(1000)
        with self.assertRaises(InsufficientCash):
            pf.buy("A", 11, 100.0, 0, D)
        self.assertEqual(pf.cash, 1000)
        with self.assertRaises(PortfolioError):
            pf.sell("A", 1, 100.0, 0, D)
        pf.buy("A", 5, 100.0, 0, D)
        with self.assertRaises(PortfolioError):
            pf.sell("A", 6, 100.0, 0, D)

    def test_identitaet_equity_gleich_start_plus_pnl_plus_dividenden(self):
        pf = Portfolio(10_000)
        pf.buy("A", 10, 100.0, 2.0, D)
        pf.buy("B", 20, 50.0, 3.0, D)
        pf.mark({"A": 105.0, "B": 48.0})
        pf.apply_dividend("A", 0.3, D)
        pf.sell("B", 5, 49.0, 0.5, D)
        pf.mark({"B": 47.0})
        self.assertAlmostEqual(pf.equity(), pf.initial_cash + pf.realized_pnl + pf.unrealized_pnl + pf.dividends_total, places=9)

    def test_ungueltige_eingaben(self):
        with self.assertRaises(PortfolioError):
            Portfolio(0)
        with self.assertRaises(PortfolioError):
            Portfolio(100).buy("A", 0, 10, 0, D)


class TestRisk(unittest.TestCase):
    def setUp(self):
        self.pf = Portfolio(100_000)
        self.rm = RiskManager(RiskConfig.beispiel_test())     # 10 % / 20 % Cash / 80 % Investition

    def test_positionsgroesse_wird_abgelehnt(self):
        d = self.rm.check_buy(self.pf, "A", 150, 100.0, 0, {})              # 15.000 = 15 % > 10 %
        self.assertFalse(d.approved)
        self.assertTrue(any("Positionsgroesse" in g for g in d.reasons))
        self.assertTrue(self.rm.check_buy(self.pf, "A", 100, 100.0, 0, {}).approved)   # genau 10 % ist erlaubt

    def test_cash_reserve_und_exposure_werden_durchgesetzt(self):
        for s in "ABCDEFGH":
            self.pf.buy(s, 100, 100.0, 0, D)                                # 8 x 10 % = 80 % investiert, 20 % Cash
        d = self.rm.check_buy(self.pf, "I", 10, 100.0, 0, {})
        self.assertFalse(d.approved)
        self.assertTrue(any("Cash-Reserve" in g for g in d.reasons))
        self.assertTrue(any("Gesamtinvestition" in g for g in d.reasons))
        self.assertEqual(self.rm.max_buy_value(self.pf, "I", {}), 0.0)

    def test_max_offene_positionen_drawdown_und_risiko_je_position(self):
        rm = RiskManager(RiskConfig(max_open_positions=1, max_drawdown_pct=0.10, max_risk_per_position_pct=0.01, stop_loss_pct=0.05))
        pf = Portfolio(100_000)
        pf.buy("A", 10, 100.0, 0, D)
        self.assertFalse(rm.check_buy(pf, "B", 10, 100.0, 0, {}).approved)           # zweite Position
        self.assertFalse(rm.check_buy(Portfolio(100_000), "A", 300, 100.0, 0, {}).approved)   # 30.000 * 5 % = 1,5 % Risiko > 1 %
        self.assertTrue(rm.check_buy(Portfolio(100_000), "A", 200, 100.0, 0, {}).approved)    # 20.000 * 5 % = 1,0 %
        d = rm.check_buy(Portfolio(90_000), "A", 1, 100.0, 0, {}, peak_equity=100_000)        # 10 % Drawdown
        self.assertFalse(d.approved)
        self.assertTrue(any("Drawdown" in g for g in d.reasons))

    def test_engine_haelt_risikogrenzen_ein_acht_positionen_neunte_abgelehnt(self):
        cfg = BacktestConfig(initial_cash=100_000, fee_rate=0, slippage_rate=0, position_size_pct=0.10)
        daten = {f"S{i:02d}": frame([100.0] * 5, [100.0] * 5) for i in range(12)}
        r = BacktestEngine(daten, Scripted({"2024-01-01": 1}), cfg, risk=RiskConfig.beispiel_test()).run()
        gefuellt = [o for o in r.orders if o.status == "filled"]
        self.assertEqual(len(gefuellt), 8)
        self.assertEqual(len(r.rejected_orders), 4)
        pf = r.portfolio
        self.assertAlmostEqual(pf.cash / pf.equity(), 0.20, places=9)
        self.assertLessEqual(pf.invested() / pf.equity(), 0.80 + 1e-9)
        for p in pf.positions.values():
            self.assertLessEqual(p.market_value / pf.equity(), 0.10 + 1e-9)

    def test_positionsgroesse_wird_bei_hohem_zielgewicht_begrenzt(self):
        cfg = BacktestConfig(initial_cash=100_000, fee_rate=0, slippage_rate=0, position_size_pct=0.5)
        r = BacktestEngine({"A": frame([100.0] * 4, [100.0] * 4)}, Scripted({"2024-01-01": 1}), cfg, risk=RiskConfig.beispiel_test()).run()
        self.assertEqual(r.portfolio.positions["A"].quantity, 100)         # 10 % statt der gewuenschten 50 %

    def test_verkaeufe_sind_immer_erlaubt_auch_bei_drawdown_stopp(self):
        cfg = BacktestConfig(initial_cash=10_000, fee_rate=0, slippage_rate=0, position_size_pct=1.0)
        d = frame([100, 100, 50, 50, 50], [100, 60, 50, 50, 50])
        r = BacktestEngine({"A": d}, Scripted({"2024-01-01": 1, "2024-01-02": 0}), cfg, risk=RiskConfig(max_drawdown_pct=0.2)).run()
        self.assertEqual([o.status for o in r.orders], ["filled", "filled"])
        self.assertEqual(r.portfolio.positions, {})


class TestMetrics(unittest.TestCase):
    def kurve(self, werte):
        idx = pd.bdate_range("2024-01-01", periods=len(werte))
        return pd.DataFrame({"equity": werte, "cash": werte, "invested": 0.0}, index=idx)

    def test_sharpe_sortino_drawdown_mit_bekannten_werten(self):
        eq = pd.Series([100.0, 110.0, 99.0, 108.9])               # Renditen +10 %, -10 %, +10 %
        r = M.daily_returns(eq)
        self.assertTrue(np.allclose(r, [0.1, -0.1, 0.1]))
        # mean = 1/30 ; std(ddof=1) = sqrt(0,013333) ; sharpe = mean/std*sqrt(252)
        self.assertAlmostEqual(M.sharpe_ratio(r), (1 / 30) / math.sqrt(0.0133333333333) * math.sqrt(252), places=6)
        self.assertAlmostEqual(M.sharpe_ratio(r), 4.58258, places=4)
        # Abwaertsabweichung = sqrt(mean(min(r,0)^2)) = sqrt(0,01/3) ; sortino = mean/dd*sqrt(252)
        self.assertAlmostEqual(M.sortino_ratio(r), (1 / 30) / math.sqrt(0.01 / 3) * math.sqrt(252), places=6)
        dd = M.drawdown_series(eq)
        self.assertTrue(np.allclose(dd, [0, 0, -0.1, 108.9 / 110 - 1]))

    def test_sonderfaelle(self):
        self.assertIsNone(M.sharpe_ratio(pd.Series([0.0, 0.0, 0.0])))        # keine Streuung
        self.assertIsNone(M.sharpe_ratio(pd.Series([0.01])))                 # zu wenige Beobachtungen
        self.assertIsNone(M.sortino_ratio(pd.Series([0.01, 0.02, 0.03])))    # keine Verluste -> undefiniert
        self.assertIsNone(M.sortino_ratio(pd.Series([0.01])))

    def test_compute_metrics_ohne_rendite_und_mit_zu_wenig_daten(self):
        pf = Portfolio(100.0)
        m = M.compute_metrics(self.kurve([100.0] * 5), pf)
        self.assertEqual((m["net_return"], m["max_drawdown"], m["average_drawdown"]), (0.0, 0.0, 0.0))
        self.assertIsNone(m["sharpe"])
        self.assertEqual(m["annualized_return"], 0.0)
        eins = M.compute_metrics(self.kurve([100.0]), pf)
        self.assertIsNone(eins["annualized_return"])
        self.assertIsNone(eins["volatility"])
        self.assertIsNone(eins["sharpe"])

    def test_drawdown_nach_verlusten_und_durchschnitt(self):
        pf = Portfolio(100.0)
        m = M.compute_metrics(self.kurve([100.0, 110.0, 99.0, 108.9]), pf)
        self.assertAlmostEqual(m["max_drawdown"], -0.1, places=12)
        self.assertAlmostEqual(m["average_drawdown"], (-0.1 + (108.9 / 110 - 1)) / 2, places=12)

    def test_trade_statistik_profit_factor(self):
        def t(pnl, tage):
            return Trade("A", D, D + dt.timedelta(days=tage), 1, 100, 100 + pnl, pnl, 0, tage)
        s = M.trade_stats([t(100, 2), t(-50, 4), t(50, 6)])
        self.assertEqual((s["number_of_trades"], s["winning_trades"], s["losing_trades"]), (3, 2, 1))
        self.assertAlmostEqual(s["win_rate"], 2 / 3)
        self.assertAlmostEqual(s["profit_factor"], 3.0)            # 150 / 50
        self.assertAlmostEqual(s["average_win"], 75.0)
        self.assertAlmostEqual(s["average_loss"], -50.0)
        self.assertAlmostEqual(s["average_holding_days"], 4.0)
        nur_verluste = M.trade_stats([t(-10, 1)])
        self.assertEqual(nur_verluste["profit_factor"], 0.0)
        self.assertIsNone(nur_verluste["average_win"])

    def test_annualisierte_rendite_und_volatilitaet(self):
        pf = Portfolio(100.0)
        werte = [100.0 * 1.01 ** i for i in range(11)]             # 10 Perioden je +1 %
        m = M.compute_metrics(self.kurve(werte), pf)
        self.assertAlmostEqual(m["annualized_return"], 1.01 ** 252 - 1, places=6)
        self.assertAlmostEqual(m["volatility"], 0.0, places=9)     # konstante Rendite -> keine Streuung

    def test_risikofreier_zins_wird_beruecksichtigt(self):
        r = pd.Series([0.01, -0.005, 0.012, 0.003])
        self.assertLess(M.sharpe_ratio(r, 0.05), M.sharpe_ratio(r, 0.0))


if __name__ == "__main__":
    unittest.main()
