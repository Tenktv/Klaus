"""Marktdaten-Pruefung (Vollstaendigkeit, Kalender, Ausreisser, Adjusted Close, Dividenden, Splits) und Quellen-Verifikation."""
import unittest

import numpy as np
import pandas as pd

from tests._quant_helpers import frame
from quant import data as D
from quant.calendar import MarketCalendar
from quant.corporate_actions import CorporateActions
from quant.data_check import check_prices, compare_frames, verify_source

NYSE = MarketCalendar("NYSE")


def nyse_frame(start="2024-11-18", end="2024-12-06"):
    idx = NYSE.sessions(start, end)
    c = 100 + np.arange(len(idx)) * 0.1
    return frame(c, c + 0.05, dates=idx)


class TestCheck(unittest.TestCase):
    def test_saubere_daten_sind_ok(self):
        r = check_prices(nyse_frame(), "A", NYSE)
        self.assertEqual((r.status, r.issues), ("ok", []))
        self.assertEqual(r.stats["missing_sessions"], 0)

    def test_fehlende_handelstage_und_zeilen_an_feiertagen(self):
        d = nyse_frame()
        d = d.drop(d.index[3])                                          # echter Ausfall
        r = check_prices(d, "A", NYSE)
        self.assertIn("missing_sessions", r.codes())
        self.assertEqual(r.stats["missing_sessions"], 1)
        feiertag = pd.concat([nyse_frame(), frame([100], [100], dates=pd.DatetimeIndex(["2024-11-28"]))]).sort_index()   # Thanksgiving
        r2 = check_prices(feiertag, "A", NYSE)
        self.assertEqual(r2.status, "errors")
        self.assertIn("non_session_rows", r2.codes())

    def test_viel_fehlt_ist_ein_fehler(self):
        d = nyse_frame()
        r = check_prices(d.iloc[::3], "A", NYSE)
        self.assertEqual(r.status, "errors")

    def test_doppelte_nan_und_unsortierte_rohdaten(self):
        d = nyse_frame()
        roh = pd.concat([d, d.iloc[[2]]]).iloc[::-1]
        roh.iloc[4, roh.columns.get_loc("close")] = np.nan
        c = check_prices(roh, "A").codes()
        self.assertTrue({"duplicate_timestamps", "unsorted", "missing_prices"} <= set(c))

    def test_ausreisser_und_split_erklaerung(self):
        d = nyse_frame()
        d.iloc[8:, d.columns.get_indexer(["open", "high", "low", "close"])] *= 1.5          # +50 % Sprung
        self.assertIn("outlier_return", check_prices(d, "A").codes())
        halb = nyse_frame()
        halb.iloc[8:, halb.columns.get_indexer(["open", "high", "low", "close"])] *= 0.5     # 2:1-Split roh
        ex = halb.index[8]
        ok = check_prices(halb, "A", actions=CorporateActions(splits=pd.Series({ex: 2.0})))
        self.assertNotIn("outlier_return", ok.codes())
        self.assertNotIn("split_without_jump", ok.codes())
        ohne = check_prices(halb, "A")
        self.assertIn("outlier_return", ohne.codes())

    def test_split_laut_quelle_aber_kein_sprung_in_rohpreisen(self):
        d = nyse_frame()
        r = check_prices(d, "A", actions=CorporateActions(splits=pd.Series({d.index[8]: 4.0})))
        self.assertIn("split_without_jump", r.codes())
        adj = check_prices(d, "A", actions=CorporateActions(splits=pd.Series({d.index[8]: 4.0}), prices_split_adjusted=True))
        self.assertNotIn("split_without_jump", adj.codes())        # bereinigte Preise: kein Sprung erwartet
        sprung = nyse_frame()
        sprung.iloc[8:, sprung.columns.get_indexer(["open", "high", "low", "close"])] *= 0.25
        r2 = check_prices(sprung, "A", actions=CorporateActions(splits=pd.Series({sprung.index[8]: 4.0}), prices_split_adjusted=True))
        self.assertIn("split_not_adjusted", r2.codes())

    def test_adjusted_close_konsistenz_und_dividenden(self):
        d = nyse_frame()
        ex = d.index[10]
        faktor = np.where(d.index < ex, 0.99, 1.0)                  # Dividenden-Anpassung: Verhaeltnis steigt zum Ende hin
        d["adj_close"] = d["close"] * faktor
        ok = check_prices(d, "A", actions=CorporateActions(pd.Series({ex: 1.0})))
        self.assertEqual(ok.status, "ok")
        self.assertIn("adj_jump_without_action", check_prices(d, "A", actions=CorporateActions()).codes())   # Aktionsliste leer -> Sprung unerklaert
        self.assertNotIn("adj_jump_without_action", check_prices(d, "A").codes())                           # ohne Aktionsliste kein Vergleich moeglich
        falsch = check_prices(d, "A", actions=CorporateActions(pd.Series({d.index[3]: 1.0})))
        self.assertIn("adj_jump_without_action", falsch.codes())
        d2 = nyse_frame()
        d2["adj_close"] = d2["close"] * 1.1
        self.assertIn("adj_above_close", check_prices(d2, "A").codes())
        riesig = check_prices(nyse_frame(), "A", actions=CorporateActions(pd.Series({ex: 50.0})))
        self.assertIn("dividend_implausible", riesig.codes())

    def test_flache_kurse_und_nullvolumen(self):
        d = nyse_frame("2024-10-01", "2024-12-06")
        d.iloc[3:12, d.columns.get_loc("close")] = 100.0
        d["volume"] = 0.0
        c = check_prices(d, "A").codes()
        self.assertIn("flat_prices", c)
        self.assertIn("zero_volume", c)


class TestQuellen(unittest.TestCase):
    def quelle(self, fehler=None, daten=None):
        class Q(D.MarketDataSource):
            name = "fake"

            def fetch(self, symbol, start=None, end=None):
                if fehler:
                    raise fehler
                df, rep = D.validate_ohlcv(nyse_frame() if daten is None else daten, symbol)
                return D.MarketData(symbol, df, CorporateActions(), "fake", rep)
        return Q()

    def test_nicht_erreichbare_quelle_ist_not_verified_nie_ok(self):
        res = verify_source(self.quelle(D.DataError("Yahoo-Abruf fehlgeschlagen (Netzwerk)")), ["AAPL", "SPY"], calendar=NYSE)
        self.assertEqual(res["overall"], "not_verified")
        self.assertEqual({v["status"] for v in res["symbols"].values()}, {"not_verified"})
        self.assertIn("Netzwerk", res["symbols"]["AAPL"]["reason"])

    def test_gute_quelle_ok_und_schlechte_quelle_mit_problemen(self):
        self.assertEqual(verify_source(self.quelle(), ["A"], calendar=NYSE)["overall"], "ok")
        d = nyse_frame().drop(nyse_frame().index[2:12])
        res = verify_source(self.quelle(daten=d), ["A"], calendar=NYSE)
        self.assertEqual(res["overall"], "errors")
        self.assertIn("missing_sessions", [i["code"] for i in res["symbols"]["A"]["issues"]])
        self.assertIn("kein Beweis", res["note"])

    def test_ein_symbol_nicht_verifiziert_macht_gesamtergebnis_nicht_ok(self):
        class Gemischt(D.MarketDataSource):
            name = "mix"

            def fetch(s, symbol, start=None, end=None):
                if symbol == "X":
                    raise D.DataError("weg")
                return self_q.fetch(symbol)
        self_q = self.quelle()
        res = verify_source(Gemischt(), ["A", "X"], calendar=NYSE)
        self.assertEqual((res["symbols"]["A"]["status"], res["overall"]), ("ok", "not_verified"))

    def test_quellenabgleich(self):
        a, b = nyse_frame(), nyse_frame()
        self.assertEqual(compare_frames(a, b)["status"], "ok")
        b.iloc[5, b.columns.get_loc("close")] *= 1.05
        r = compare_frames(a, b)
        self.assertEqual((r["status"], r["mismatches"]), ("mismatch", 1))
        self.assertEqual(compare_frames(a, a.iloc[:0])["status"], "not_verified")


if __name__ == "__main__":
    unittest.main()
