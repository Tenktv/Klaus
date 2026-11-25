"""Strategien (EMA, RSI), Walk-Forward und zeitliche Aufteilung, Sicherheits-Checks am Code."""
import re
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from tests._quant_helpers import frame, random_walk
from quant import validation as V
from quant.backtest import BacktestEngine
from quant.config import BacktestConfig
from quant.strategies import EmaCrossStrategy, RsiTrendStrategy, wilder_rsi


class TestEma(unittest.TestCase):
    def test_trend_signale_und_warmup(self):
        up = frame(list(range(10, 110)), list(range(10, 110)))
        s = EmaCrossStrategy(3, 8).generate_signals(up)
        self.assertTrue(s.iloc[:7].isna().all())             # Warmup: slow-1 Werte NaN
        self.assertTrue((s.iloc[7:] == 1.0).all())
        dn = frame(list(range(110, 10, -1)), list(range(110, 10, -1)))
        self.assertTrue((EmaCrossStrategy(3, 8).generate_signals(dn).iloc[7:] == 0.0).all())

    def test_parameter_und_update(self):
        st = EmaCrossStrategy()
        self.assertEqual(st.get_parameters(), {"fast": 20, "slow": 50})
        self.assertTrue(np.isnan(st.update(random_walk(30))))    # zu wenig Historie
        with self.assertRaises(ValueError):
            EmaCrossStrategy(50, 20)

    def test_backtest_mit_ema_20_50_ist_stabil_und_nutzt_nur_naechstes_open(self):
        d = random_walk(400, seed=11)
        r = BacktestEngine({"AAA": d}, EmaCrossStrategy(), BacktestConfig()).run()
        for o in r.orders:
            if o.status == "filled":
                self.assertGreater(o.exec_date, o.signal_date)
                self.assertAlmostEqual(o.ref_open, float(d.at[pd.Timestamp(o.exec_date), "open"]))
        self.assertGreaterEqual(r.portfolio.cash, 0)


class TestRsi(unittest.TestCase):
    def test_wilder_rsi_handrechnung_periode_2(self):
        # Kurse 10,11,10,11 ; alpha = 1/2 : Zeitpunkt 2: avg_gain 0,5, avg_loss 0,5 -> RSI 50 ; Zeitpunkt 3: 0,75 / 0,25 -> RSI 75
        r = wilder_rsi(pd.Series([10.0, 11.0, 10.0, 11.0]), 2)
        self.assertTrue(r.iloc[:2].isna().all())
        self.assertAlmostEqual(r.iloc[2], 50.0, places=9)
        self.assertAlmostEqual(r.iloc[3], 75.0, places=9)

    def test_rsi_grenzfaelle(self):
        self.assertEqual(wilder_rsi(pd.Series(np.arange(1.0, 40.0)), 14).iloc[-1], 100.0)       # nur Gewinne
        self.assertEqual(wilder_rsi(pd.Series(np.arange(40.0, 1.0, -1)), 14).iloc[-1], 0.0)    # nur Verluste
        self.assertEqual(wilder_rsi(pd.Series([5.0] * 30), 14).iloc[-1], 50.0)                 # konstant
        r = wilder_rsi(random_walk(500, seed=2)["close"], 14).dropna()
        self.assertTrue(((r >= 0) & (r <= 100)).all())

    def test_regeln_einstieg_nur_mit_trendfilter(self):
        d = random_walk(600, seed=5, vol=0.02)
        st = RsiTrendStrategy(5, 30, 70, 50)
        sig, rsi = st.generate_signals(d), wilder_rsi(d["close"], 5)
        trend = d["close"].rolling(50).mean()
        ein, aus = sig == 1.0, sig == 0.0
        self.assertTrue(ein.any() and aus.any())
        self.assertTrue(((rsi[ein] < 30) & (d["close"][ein] > trend[ein])).all())
        self.assertTrue(((rsi[aus] > 70) | (d["close"][aus] < trend[aus])).all())
        self.assertTrue(sig.iloc[:49].isna().all())

    def test_ungueltige_parameter(self):
        with self.assertRaises(ValueError):
            RsiTrendStrategy(oversold=70, overbought=30)


class TestValidierung(unittest.TestCase):
    def test_zeitliche_aufteilung_ohne_ueberlappung_und_in_reihenfolge(self):
        idx = pd.bdate_range("2020-01-01", periods=100)
        s = V.time_split(idx, 0.6, 0.2)
        self.assertLess(s["train"].end, s["validation"].start)
        self.assertLess(s["validation"].end, s["out_of_sample"].start)
        self.assertEqual((s["train"].start, s["out_of_sample"].end), (idx[0], idx[-1]))
        self.assertEqual(idx.get_loc(s["train"].end) + 1, 60)
        with self.assertRaises(ValueError):
            V.time_split(idx, 0.9, 0.2)
        with self.assertRaises(ValueError):
            V.time_split(idx[::-1])

    def test_walk_forward_fenster(self):
        idx = pd.bdate_range("2020-01-01", periods=100)
        w = V.walk_forward_windows(idx, 40, 20)
        self.assertEqual(len(w), 3)
        for a in w:
            self.assertLess(a["train"].end, a["test"].start)
        self.assertLess(w[0]["test"].end, w[1]["test"].end + pd.Timedelta(days=1))
        self.assertEqual(w[1]["train"].start, idx[20])

    def test_walk_forward_testfenster_beeinflusst_parameterwahl_nicht(self):
        d = random_walk(300, seed=9)
        grid = {"fast": [3, 5], "slow": [10, 20]}
        a = V.walk_forward({"A": d}, lambda fast, slow: EmaCrossStrategy(fast, slow), grid, train_len=120, test_len=60, warmup=30)
        d2 = d.copy()
        d2.iloc[150:, d2.columns.get_indexer(["open", "high", "low", "close"])] *= 1.7     # nur Zukunft des 1. Fensters veraendern
        b = V.walk_forward({"A": d2}, lambda fast, slow: EmaCrossStrategy(fast, slow), grid, train_len=120, test_len=60, warmup=30)
        self.assertEqual(a[0]["params"], b[0]["params"])               # Auswahl nur aus Trainingsdaten
        self.assertEqual(a[0]["train_score"], b[0]["train_score"])
        self.assertGreaterEqual(len(a), 2)
        for e in a:
            self.assertLess(pd.Timestamp(e["data_used"]["train"][1]), pd.Timestamp(e["data_used"]["test"][1]))
            self.assertLessEqual(pd.Timestamp(e["data_used"]["train"][1]), e["test"].start - pd.Timedelta(days=1))   # Training endet vor dem Test
            self.assertIn("net_return", e["test_metrics"])


class TestSicherheit(unittest.TestCase):
    QUANT = Path(__file__).resolve().parent.parent / "quant"

    def test_kein_netzwerk_oder_broker_code_ausser_dem_datenadapter(self):
        for f in self.QUANT.rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            for verboten in ("alpaca", "requests", "submit_order", "place_order", "ALPACA_", "api_key", "API_KEY", "urllib.request", "socket"):
                self.assertNotIn(verboten, text, f"{f.name}: {verboten}")

    def test_keine_geheimnisse_im_paket(self):
        for f in self.QUANT.rglob("*.py"):
            self.assertIsNone(re.search(r"(sk-|gsk_|AIza)[A-Za-z0-9_-]{10,}", f.read_text(encoding="utf-8")), f.name)


if __name__ == "__main__":
    unittest.main()
