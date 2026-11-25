"""Dividenden und Splits als Ereignisse - nie ueber Adjusted Close, nie doppelt."""
import unittest

import pandas as pd

from tests._quant_helpers import Scripted, frame
from quant.backtest import BacktestEngine
from quant.config import BacktestConfig
from quant.corporate_actions import CorporateActions

NULL = BacktestConfig(initial_cash=10_000, fee_rate=0, slippage_rate=0, position_size_pct=1.0)   # 100 Stueck zu 100


def kurse(n=6, preis=100.0):
    return frame([preis] * n, [preis] * n)


class TestDividenden(unittest.TestCase):
    def lauf(self, data=None, actions=None, script=None, cfg=NULL):
        return BacktestEngine({"A": kurse() if data is None else data}, Scripted({"2024-01-01": 1} if script is None else script), cfg, actions={"A": actions} if actions else None).run()

    def test_dividende_wird_am_ex_tag_als_cash_gebucht(self):
        # Kauf Tag2 (02.01.) zum Open, 100 Stueck. Ex-Tag 04.01.: 0,50 je Aktie = 50,00 Cash.
        a = CorporateActions(pd.Series({"2024-01-04": 0.5}))
        r = self.lauf(actions=a)
        self.assertAlmostEqual(r.portfolio.dividends_total, 50.0, places=9)
        self.assertAlmostEqual(r.portfolio.cash, 50.0, places=9)           # voll investiert + Dividende
        self.assertAlmostEqual(r.equity_curve["equity"].iloc[-1], 10_050.0, places=9)
        self.assertEqual(r.portfolio.dividend_log[0]["quantity"], 100)
        self.assertEqual(str(r.portfolio.dividend_log[0]["date"]), "2024-01-04")
        self.assertAlmostEqual(r.metrics["dividends"], 50.0)

    def test_dividende_wird_nicht_ueber_adjusted_close_doppelt_verbucht(self):
        a = CorporateActions(pd.Series({"2024-01-04": 0.5}))
        ohne = self.lauf(actions=a)
        mit_adj = kurse()
        mit_adj["adj_close"] = [99.0, 99.2, 99.4, 99.9, 100.0, 100.0]       # dividendenbereinigt: darf NICHTS aendern
        r = self.lauf(data=mit_adj, actions=a)
        pd.testing.assert_frame_equal(ohne.equity_curve, r.equity_curve)
        self.assertAlmostEqual(r.portfolio.dividends_total, 50.0, places=9)  # genau einmal
        self.assertEqual(len(r.portfolio.dividend_log), 1)
        self.assertEqual(r.orders[0].ref_open, 100.0)                        # Ausfuehrung zum rohen Open, nicht zu adj_close

    def test_kauf_am_ex_tag_bekommt_keine_dividende(self):
        a = CorporateActions(pd.Series({"2024-01-02": 0.5}))                 # Kauf wird am 02.01. zum Open ausgefuehrt = Ex-Tag
        r = self.lauf(actions=a)
        self.assertEqual(r.portfolio.dividends_total, 0.0)

    def test_dividende_nicht_doppelt_bei_neuem_lauf_oder_mehreren_tagen(self):
        a = CorporateActions(pd.Series({"2024-01-03": 1.0}))
        r = self.lauf(actions=a)
        self.assertAlmostEqual(r.portfolio.dividends_total, 100.0, places=9)  # 100 Stueck * 1,00, nur einmal

    def test_dividende_ohne_position_wird_ignoriert(self):
        r = self.lauf(actions=CorporateActions(pd.Series({"2024-01-04": 0.5})), script={})
        self.assertEqual(r.portfolio.dividends_total, 0.0)

    def test_ex_tag_ohne_kerze_wird_am_naechsten_handelstag_gebucht(self):
        a = CorporateActions(pd.Series({"2024-01-06": 0.5}))                  # Samstag
        r = self.lauf(actions=a)
        self.assertAlmostEqual(r.portfolio.dividends_total, 50.0, places=9)
        self.assertEqual(str(r.portfolio.dividend_log[0]["date"]), "2024-01-06")   # Ex-Datum bleibt im Protokoll

    def test_ungueltige_aktionen_werden_abgelehnt(self):
        with self.assertRaises(ValueError):
            CorporateActions(pd.Series({"2024-01-04": -1.0}))
        with self.assertRaises(ValueError):
            CorporateActions(splits=pd.Series({"2024-01-04": 0.0}))


class TestSplits(unittest.TestCase):
    def daten(self):
        # Preis 100 bis zum 02.01. ; 2:1-Split mit Ex-Tag 04.01. -> Preis 50 (roh, wie gehandelt)
        return frame([100, 100, 100, 50, 50, 50], [100, 100, 100, 50, 50, 50])

    def test_split_passt_stueckzahl_und_einstand_an_ohne_kuenstlichen_gewinn(self):
        r = BacktestEngine({"A": self.daten()}, Scripted({"2024-01-01": 1}), NULL, actions={"A": CorporateActions(splits=pd.Series({"2024-01-04": 2.0}))}).run()
        p = r.portfolio.positions["A"]
        self.assertEqual(p.quantity, 200)
        self.assertAlmostEqual(p.avg_entry_price, 50.0, places=9)
        eq = r.equity_curve["equity"].tolist()
        self.assertEqual(eq, [10_000.0] * 6)                                   # Equity bleibt ueber den Split konstant
        self.assertAlmostEqual(r.portfolio.unrealized_pnl, 0.0, places=9)
        self.assertEqual(r.portfolio.realized_pnl, 0.0)
        s = r.portfolio.split_log[0]
        self.assertAlmostEqual(s["value_before"], s["value_after"], places=9)

    def test_umgekehrter_split_1_zu_10(self):
        d = frame([10, 10, 10, 100, 100, 100], [10, 10, 10, 100, 100, 100])
        r = BacktestEngine({"A": d}, Scripted({"2024-01-01": 1}), NULL, actions={"A": CorporateActions(splits=pd.Series({"2024-01-04": 0.1}))}).run()
        p = r.portfolio.positions["A"]
        self.assertAlmostEqual(p.quantity, 100.0, places=6)    # 1000 Stueck zu 10 -> 100 zu 100
        self.assertAlmostEqual(r.equity_curve["equity"].iloc[-1], 10_000.0, places=6)

    def test_strategie_sieht_nach_dem_split_eine_kontinuierliche_historie(self):
        s = BacktestEngine({"A": self.daten()}, Scripted({}), NULL, actions={"A": CorporateActions(splits=pd.Series({"2024-01-04": 2.0}))})
        seen = []

        class Rec(Scripted):
            def update(self, history):
                seen.append(history["close"].tolist())
                return float("nan")
        s.strategies["A"] = Rec({})
        s.run()
        self.assertEqual(seen[3], [50.0, 50.0, 50.0, 50.0])        # an Tag 4 (Ex-Tag): Vergangenheit auf neues Niveau gebracht
        self.assertEqual(seen[2], [100.0, 100.0, 100.0])           # davor: keine Kenntnis des kommenden Splits (kausal)

    def test_bereits_splitbereinigte_preise_werden_nicht_doppelt_angepasst(self):
        a = CorporateActions(splits=pd.Series({"2024-01-04": 2.0}), prices_split_adjusted=True)
        r = BacktestEngine({"A": kurse()}, Scripted({"2024-01-01": 1}), NULL, actions={"A": a}).run()
        self.assertEqual(r.portfolio.positions["A"].quantity, 100)


if __name__ == "__main__":
    unittest.main()
