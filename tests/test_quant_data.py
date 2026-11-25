"""Market Data Engine: Validierung, fehlende Daten, Duplikate, Zeitzonen, Adapter, Cache."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from tests._quant_helpers import frame
from quant import data as D
from quant.backtest import BacktestEngine
from quant.config import BacktestConfig
from quant.strategies import EmaCrossStrategy


class TestValidierung(unittest.TestCase):
    def test_fehlende_daten_zeilen_werden_entfernt_und_gemeldet(self):
        f = frame([10, 11, 12, 13], [10, 11, 12, 13])
        f.iloc[2, f.columns.get_loc("close")] = np.nan
        d, rep = D.validate_ohlcv(f, "X")
        self.assertEqual((len(d), rep.nan_rows_removed, rep.rows_in, rep.rows_out), (3, 1, 4, 3))
        self.assertFalse(rep.ok)

    def test_grosse_luecken_werden_gemeldet(self):
        idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-02-01", "2024-02-02"])
        d, rep = D.validate_ohlcv(frame([1, 1, 1, 1], [1, 1, 1, 1], dates=idx), "X")
        self.assertEqual(rep.gaps, [("2024-01-03", "2024-02-01", 29)])

    def test_identische_doppelte_zeitstempel_werden_entfernt(self):
        f = frame([10, 11, 12], [10, 11, 12])
        f = pd.concat([f, f.iloc[[1]]])
        d, rep = D.validate_ohlcv(f, "X")
        self.assertEqual((len(d), rep.duplicates_removed), (3, 1))
        self.assertFalse(d.index.has_duplicates)

    def test_widerspruechliche_duplikate_sind_ein_fehler(self):
        f = frame([10, 11, 12], [10, 11, 12])
        zweite = f.iloc[[1]].copy()
        zweite["close"] = 11.4
        with self.assertRaises(D.DataError):
            D.validate_ohlcv(pd.concat([f, zweite]), "X")

    def test_unsortiert_wird_sortiert(self):
        f = frame([10, 11, 12], [10, 11, 12]).iloc[::-1]
        d, _ = D.validate_ohlcv(f, "X")
        self.assertTrue(d.index.is_monotonic_increasing)

    def test_unbrauchbare_daten_werden_abgelehnt(self):
        f = frame([10, 11, 12], [10, 11, 12])
        for schaden in ({"close": -1.0}, {"high": 1.0}, {"volume": -5.0}, {"open": 0.0}):
            g = f.copy()
            g.iloc[1, g.columns.get_loc(list(schaden)[0])] = list(schaden.values())[0]
            with self.assertRaises(D.DataError, msg=str(schaden)):
                D.validate_ohlcv(g, "X")
        with self.assertRaises(D.DataError):
            D.validate_ohlcv(f.drop(columns=["close"]), "X")
        with self.assertRaises(D.DataError):
            D.validate_ohlcv(pd.DataFrame(), "X")

    def test_zeitzonen_werden_normalisiert(self):
        f = frame([10, 11], [10, 11])
        f.index = pd.DatetimeIndex(["2024-01-02 14:30:00", "2024-01-03 14:30:00"], tz="UTC")
        d, _ = D.validate_ohlcv(f, "X")
        self.assertEqual([str(t.date()) for t in d.index], ["2024-01-02", "2024-01-03"])
        self.assertIsNone(d.index.tz)

    def test_engine_validiert_vor_dem_backtest(self):
        kaputt = frame([10, 11, 12, 13], [10, 11, 12, 13])
        kaputt.iloc[1, kaputt.columns.get_loc("close")] = -3.0
        with self.assertRaises(D.DataError):
            BacktestEngine({"X": kaputt}, EmaCrossStrategy(2, 3), BacktestConfig())

    def test_backtest_laeuft_mit_bereinigten_daten_mit_duplikaten_und_nan(self):
        f = frame([10, 11, 12, 13, 14, 15], [10, 11, 12, 13, 14, 15])
        f.iloc[3, f.columns.get_loc("open")] = np.nan
        f = pd.concat([f, f.iloc[[1]]])
        e = BacktestEngine({"X": f}, EmaCrossStrategy(2, 3), BacktestConfig())
        self.assertEqual(e.reports["X"].duplicates_removed, 1)
        self.assertEqual(e.reports["X"].nan_rows_removed, 1)
        e.run()


class TestAdapter(unittest.TestCase):
    CSV = "Date,Open,High,Low,Close,Adj Close,Volume\n2024-01-02,10,11,9,10.5,10.4,100\n2024-01-03,10.5,12,10,11,10.9,120\n"

    def test_csv_und_json_und_dataframe(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "A.csv"
            p.write_text(self.CSV)
            d, rep = D.load_csv(p, "A")
            self.assertEqual(list(d.columns), ["open", "high", "low", "close", "volume", "adj_close"])
            self.assertEqual(d["close"].tolist(), [10.5, 11.0])
        j = json.dumps([{"date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 5}])
        self.assertEqual(len(D.load_json(j, "A")[0]), 1)
        self.assertEqual(len(D.from_dataframe(frame([1, 2], [1, 2]), "A")[0]), 2)
        with self.assertRaises(D.DataError):
            D.load_json("kein json", "A")
        with self.assertRaises(D.DataError):
            D.load_csv("/gibt/es/nicht.csv", "A")

    def test_csv_ordner_quelle_mit_aktionen_und_pfadschutz(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "A.csv").write_text(self.CSV)
            (Path(t) / "A_actions.json").write_text(json.dumps({"dividends": {"2024-01-03": 0.2}, "splits": {"2024-01-03": 2}}))
            md = D.CsvDirSource(t).fetch("A")
            self.assertEqual(md.actions.dividends.iloc[0], 0.2)
            self.assertEqual(md.actions.splits.iloc[0], 2)
            self.assertEqual(md.source, "csv")
            with self.assertRaises(D.DataError):
                D.CsvDirSource(t).fetch("../etc/passwd")
            self.assertEqual(len(D.CsvDirSource(t).fetch("A", start="2024-01-03").prices), 1)

    def test_cache_holt_nur_einmal_von_der_quelle(self):
        class Quelle(D.MarketDataSource):
            name = "fake"
            n = 0

            def fetch(self, symbol, start=None, end=None):
                Quelle.n += 1
                df, rep = D.validate_ohlcv(frame([1, 2, 3], [1, 2, 3]), symbol)
                from quant.corporate_actions import CorporateActions
                return D.MarketData(symbol, df, CorporateActions(pd.Series({"2024-01-02": 0.1})), "fake", rep)
        with tempfile.TemporaryDirectory() as t:
            c = D.CachedSource(Quelle(), t)
            a, b = c.fetch("A"), c.fetch("A")
            self.assertEqual(Quelle.n, 1)
            self.assertTrue(a.source.endswith("miss") and b.source.endswith("hit"))
            pd.testing.assert_frame_equal(a.prices, b.prices, check_freq=False)
            self.assertEqual(b.actions.dividends.iloc[0], 0.1)
            for f in Path(t).glob("*.csv"):
                f.write_text("kaputt")                                   # kaputter Cache -> neu holen
            c.fetch("A")
            self.assertEqual(Quelle.n, 2)

    def test_yahoo_adapter_mit_gespieltem_yfinance(self):
        h = pd.DataFrame({"Open": [10, 11], "High": [12, 12], "Low": [9, 10], "Close": [11, 11.5], "Adj Close": [10.8, 11.5], "Volume": [100, 200],
                          "Dividends": [0.0, 0.25], "Stock Splits": [0.0, 0.0]}, index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="America/New_York"))
        fake = types.SimpleNamespace(Ticker=lambda s: types.SimpleNamespace(history=lambda **kw: (self.assertFalse(kw["auto_adjust"]), h)[1]))
        with mock.patch.dict(sys.modules, {"yfinance": fake}):
            md = D.YahooSource().fetch("AAPL")
        self.assertEqual(md.source, "yahoo")
        self.assertTrue(md.actions.prices_split_adjusted)
        self.assertEqual(md.actions.dividends.iloc[0], 0.25)
        self.assertEqual(md.prices["close"].tolist(), [11.0, 11.5])      # roher Close, nicht Adj Close
        with mock.patch.dict(sys.modules, {"yfinance": None}):
            with self.assertRaises(D.DataError):
                D.YahooSource().fetch("AAPL")


if __name__ == "__main__":
    unittest.main()
