"""Paper-Broker: Market/Limit/Stop, nicht ausgefuehrte Orders, Kosten, Cash, Risiko, Marktdaten-Fehler, Feiertage, Neustart/Wiederherstellung,
Gleichheit mit dem Backtest."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from tests._quant_helpers import random_walk
from quant.backtest import BacktestEngine
from quant.calendar import MarketCalendar
from quant.config import BacktestConfig, RiskConfig
from quant.paper import PaperBroker, PaperOrderError, PaperStateError, PaperTrader
from quant.strategies import EmaCrossStrategy

CFG = BacktestConfig(initial_cash=10_000, fee_rate=0.001, slippage_rate=0.002, position_size_pct=0.5)


def bar(o, h, l, c, v=1000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def tag(n):
    """n-ter Handelstag ab Montag 2024-01-01 (nur Mo-Fr)."""
    return pd.bdate_range("2024-01-01", periods=n + 1)[n].date()


class PaperTest(unittest.TestCase):
    def broker(self, **kw):
        return PaperBroker(kw.pop("cfg", CFG), kw.pop("risk", None), **kw)


class TestMarket(PaperTest):
    def test_market_kauf_zum_open_der_naechsten_kerze_mit_kosten(self):
        b = self.broker()
        o = b.submit("A", "buy", 10)
        self.assertEqual(o.status, "open")                              # vor der ersten Kerze passiert nichts
        self.assertEqual(b.pf.cash, 10_000)
        b.process_day(tag(0), {"A": bar(100, 105, 99, 104)})
        self.assertEqual((o.status, o.quantity), ("filled", 10))
        self.assertAlmostEqual(o.exec_price, 100.2, places=9)           # Open 100 + 0,2 % Slippage
        self.assertAlmostEqual(o.fee, 1.002, places=9)                  # 0,1 % von 10 * 100,2
        self.assertAlmostEqual(o.slippage_cost, 2.0, places=9)
        self.assertAlmostEqual(b.pf.cash, 10_000 - 1002 - 1.002, places=9)
        self.assertAlmostEqual(b.pf.equity(), 10_000 - 1002 - 1.002 + 1040, places=9)     # Bewertung zum Schluss 104
        self.assertEqual(str(o.exec_date), str(tag(0)))

    def test_market_verkauf_realisiert_gewinn_und_cash(self):
        b = self.broker()
        b.submit("A", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        s = b.submit("A", "sell", 10)
        b.process_day(tag(1), {"A": bar(110, 112, 109, 111)})
        self.assertAlmostEqual(s.exec_price, 109.78, places=9)
        erwartet = (109.78 - 100.2) * 10 - 10 * 109.78 * 0.001 - 10 * 100.2 * 0.001
        self.assertAlmostEqual(b.pf.realized_pnl, erwartet, places=9)
        self.assertEqual(b.pf.positions, {})
        self.assertAlmostEqual(b.pf.equity(), 10_000 + erwartet, places=9)

    def test_zielgewicht_market_kauf_wird_beim_fill_dimensioniert(self):
        b = self.broker()
        o = b.submit("A", "buy", target_pct=0.5)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        self.assertEqual(o.quantity, 49)                                # 5000 / (100,2 * 1,001) = 49,85


class TestLimit(PaperTest):
    def test_limit_kauf_nicht_erreicht_bleibt_offen_und_wird_spaeter_zu_limit_ausgefuehrt(self):
        b = self.broker()
        o = b.submit("A", "buy", 10, "limit", limit_price=98)
        b.process_day(tag(0), {"A": bar(100, 102, 99, 101)})            # Tief 99 > 98: kein Fill
        self.assertEqual(o.status, "open")
        self.assertEqual((b.pf.cash, b.pf.positions), (10_000, {}))
        self.assertEqual(b.pf.equity(), 10_000)                          # nichts kuenstlich ausgefuehrt
        b.process_day(tag(1), {"A": bar(99, 100, 97, 98)})              # Tief 97 < 98 (durchgehandelt)
        self.assertEqual(o.status, "filled")
        self.assertEqual(o.exec_price, 98.0)                            # zum Limit, ohne Slippage
        self.assertAlmostEqual(o.fee, 0.98, places=9)

    def test_limit_kauf_mit_luecke_unter_das_limit_fuellt_zum_besseren_open(self):
        b = self.broker()
        o = b.submit("A", "buy", 10, "limit", limit_price=98)
        b.process_day(tag(0), {"A": bar(96, 97, 95, 96)})
        self.assertAlmostEqual(o.exec_price, 96 * 1.002, places=9)      # Preisverbesserung, Slippage bleibt (<= Limit)

    def test_nur_beruehrung_reicht_standardmaessig_nicht(self):
        b = self.broker()
        o = b.submit("A", "buy", 10, "limit", limit_price=98)
        b.process_day(tag(0), {"A": bar(100, 101, 98, 100)})            # Tief == Limit
        self.assertEqual(o.status, "open")
        locker = self.broker(limit_requires_trade_through=False)
        o2 = locker.submit("A", "buy", 10, "limit", limit_price=98)
        locker.process_day(tag(0), {"A": bar(100, 101, 98, 100)})
        self.assertEqual(o2.status, "filled")

    def test_limit_verkauf(self):
        b = self.broker()
        b.submit("A", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 100.5, 99.5, 100)})
        s = b.submit("A", "sell", 10, "limit", limit_price=110)
        b.process_day(tag(1), {"A": bar(105, 109, 104, 108)})            # Hoch 109 < 110
        self.assertEqual(s.status, "open")
        b.process_day(tag(2), {"A": bar(108, 111, 107, 110)})            # Hoch 111 > 110
        self.assertEqual((s.status, s.exec_price), ("filled", 110.0))
        g = self.broker()
        g.submit("A", "buy", 10)
        g.process_day(tag(0), {"A": bar(100, 100.5, 99.5, 100)})
        s2 = g.submit("A", "sell", 10, "limit", limit_price=110)
        g.process_day(tag(1), {"A": bar(112, 113, 111, 112)})            # Luecke ueber das Limit
        self.assertAlmostEqual(s2.exec_price, 112 * 0.998, places=9)

    def test_tagesorder_verfaellt_gtc_bleibt(self):
        b = self.broker()
        tag_order = b.submit("A", "buy", 10, "limit", limit_price=90, time_in_force="day")
        gtc = b.submit("A", "buy", 10, "limit", limit_price=90)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        self.assertEqual((tag_order.status, gtc.status), ("expired", "open"))
        self.assertEqual(b.open_orders(), [gtc])
        self.assertTrue(b.cancel(gtc.id))
        self.assertEqual((gtc.status, b.cancel(gtc.id)), ("cancelled", False))


class TestStop(PaperTest):
    def mit_position(self):
        b = self.broker()
        b.submit("A", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 100.5, 99.5, 100)})
        return b

    def test_stop_verkauf_loest_aus_und_fuellt_zum_stop_minus_slippage(self):
        b = self.mit_position()
        s = b.submit("A", "sell", 10, "stop", stop_price=95)
        b.process_day(tag(1), {"A": bar(99, 100, 96, 97)})              # Tief 96 > 95: nicht ausgeloest
        self.assertEqual(s.status, "open")
        b.process_day(tag(2), {"A": bar(97, 98, 94, 95)})               # Tief 94 <= 95
        self.assertEqual(s.status, "filled")
        self.assertAlmostEqual(s.exec_price, 95 * 0.998, places=9)

    def test_stop_verkauf_mit_gap_fuellt_zum_schlechteren_open(self):
        b = self.mit_position()
        s = b.submit("A", "sell", 10, "stop", stop_price=95)
        b.process_day(tag(1), {"A": bar(90, 91, 88, 89)})               # Eroeffnung unter dem Stop
        self.assertAlmostEqual(s.exec_price, 90 * 0.998, places=9)      # nicht zum Stop-Preis 95

    def test_stop_kauf(self):
        b = self.broker()
        s = b.submit("A", "buy", 10, "stop", stop_price=105)
        b.process_day(tag(0), {"A": bar(100, 104, 99, 103)})
        self.assertEqual(s.status, "open")
        b.process_day(tag(1), {"A": bar(103, 106, 102, 105)})
        self.assertAlmostEqual(s.exec_price, 105 * 1.002, places=9)
        g = self.broker()
        s2 = g.submit("A", "buy", 10, "stop", stop_price=105)
        g.process_day(tag(0), {"A": bar(108, 109, 107, 108)})
        self.assertAlmostEqual(s2.exec_price, 108 * 1.002, places=9)


class TestEingabenCashRisiko(PaperTest):
    def test_ungueltige_orders_werden_abgelehnt_und_protokolliert(self):
        b = self.broker()
        for kw in ({"qty": -1}, {"qty": 0}, {"qty": 1.5}, {"qty": 1, "order_type": "limit"}, {"qty": 1, "order_type": "stop"},
                   {"qty": 1, "order_type": "iceberg"}, {"qty": 1, "time_in_force": "ioc"}, {"qty": float("nan")}, {"qty": None}):
            with self.assertRaises(PaperOrderError, msg=str(kw)):
                b.submit("A", "buy", **kw)
        with self.assertRaises(PaperOrderError):
            b.submit("A", "short", 1)
        self.assertEqual(len(b.errors), 10)
        self.assertEqual(b.orders, [])                                  # nichts angenommen
        self.assertTrue(PaperBroker(BacktestConfig(allow_fractional=True)).submit("A", "buy", 1.5).status == "open")

    def test_verkauf_ohne_position_und_uebermenge_werden_abgelehnt_long_only(self):
        b = self.broker()
        self.assertEqual(b.submit("A", "sell", 1).status, "rejected")
        b.submit("A", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        self.assertEqual(b.submit("A", "sell", 6).status, "open")
        self.assertEqual(b.submit("A", "sell", 6).status, "rejected")     # 6 + 6 > 10 gehaltene Stuecke
        self.assertGreaterEqual(b.pf.cash, 0)

    def test_nicht_genug_cash_wird_beim_fill_abgelehnt(self):
        b = self.broker()
        o = b.submit("A", "buy", 1000)                                  # 100.000 > 10.000
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        self.assertEqual(o.status, "rejected")
        self.assertIn("Cash", o.reason)
        self.assertEqual((b.pf.cash, b.pf.positions), (10_000, {}))

    def test_risk_manager_lehnt_ab_wie_im_backtest(self):
        b = self.broker(risk=RiskConfig.beispiel_test())               # max. 10 % je Position
        gross = b.submit("A", "buy", 50)                                # 5.000 = 50 %
        ok = b.submit("B", "buy", 10)                                   # ~1.000 = 10 %
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100), "B": bar(100, 101, 99, 100)})
        self.assertEqual(gross.status, "rejected")
        self.assertIn("Positionsgroesse", gross.reason)
        self.assertEqual(ok.status, "rejected")                        # 10 Stueck * 100,2 + Gebuehr > 10 % (Gebuehren/Slippage zaehlen mit)
        klein = b.submit("B", "buy", 9)
        b.process_day(tag(1), {"A": bar(100, 101, 99, 100), "B": bar(100, 101, 99, 100)})
        self.assertEqual(klein.status, "filled")

    def test_mehrere_positionen_und_cash(self):
        b = self.broker()
        b.submit("A", "buy", 10)
        b.submit("B", "buy", 20)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100), "B": bar(50, 51, 49, 50)})
        self.assertEqual(sorted(b.pf.positions), ["A", "B"])
        erwartet_cash = 10_000 - (10 * 100.2 * 1.001) - (20 * 50.1 * 1.001)
        self.assertAlmostEqual(b.pf.cash, erwartet_cash, places=9)
        self.assertEqual(len(b.snapshot()["positions"]), 2)
        self.assertAlmostEqual(b.pf.equity(), b.pf.initial_cash + b.pf.realized_pnl + b.pf.unrealized_pnl, places=9)
        self.assertIsNotNone(b.performance())


class TestMarktdaten(PaperTest):
    def test_fehlerhafte_kerze_wird_verworfen_andere_symbole_laufen_weiter(self):
        b = self.broker()
        kaputt, gut = b.submit("A", "buy", 10), b.submit("B", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 90, 99, 100), "B": bar(50, 51, 49, 50)})    # High < Low
        self.assertEqual(kaputt.status, "open")                         # nicht ausgefuehrt, bleibt offen
        self.assertEqual(gut.status, "filled")
        self.assertEqual([e["type"] for e in b.errors], ["bad_bar"])
        self.assertNotIn("A", b.last_bars)
        for schlecht in ({"open": float("nan"), "high": 1, "low": 1, "close": 1}, {"open": -1, "high": 1, "low": -2, "close": 1}, {"open": 1}):
            b.process_day(tag(1), {"A": schlecht})
            b.last_day = None                                           # gleichen Tag erneut zulassen, um jede Variante zu pruefen
        self.assertEqual(len(b.errors), 4)

    def test_doppelte_lieferung_wird_ignoriert(self):
        b = self.broker()
        b.submit("A", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        cash = b.pf.cash
        self.assertEqual(b.process_day(tag(0), {"A": bar(1, 1, 1, 1)}), [])
        self.assertEqual(b.process_day(tag(0) - pd.Timedelta(days=3), {"A": bar(1, 1, 1, 1)}), [])
        self.assertEqual(b.pf.cash, cash)
        self.assertEqual(len(b.pf.equity_curve), 1)
        self.assertEqual(sum(e["type"] == "day_ignored" for e in b.events), 2)

    def test_boersenfeiertag_wird_nicht_verarbeitet(self):
        b = self.broker(calendar=MarketCalendar("NYSE"))
        o = b.submit("A", "buy", 10)
        b.process_day("2024-11-28", {"A": bar(100, 101, 99, 100)})      # Thanksgiving
        self.assertEqual((o.status, b.last_day), ("open", None))
        self.assertEqual(b.errors[0]["type"], "non_session_day")
        b.process_day("2024-11-29", {"A": bar(100, 101, 99, 100)})
        self.assertEqual(o.status, "filled")

    def test_feiertag_ist_keine_datenluecke_aber_ein_echter_ausfall_schon(self):
        b = self.broker(calendar=MarketCalendar("NYSE"))
        b.process_day("2024-11-26", {"A": bar(100, 101, 99, 100)})
        b.process_day("2024-11-29", {"A": bar(100, 101, 99, 100)})      # 27. fehlt (echt), 28. ist Feiertag
        luecken = [e for e in b.events if e["type"] == "data_gap"]
        self.assertEqual([e["missed_sessions"] for e in luecken], [1])
        b.process_day("2024-12-02", {"A": bar(100, 101, 99, 100)})      # keine Luecke (Wochenende)
        self.assertEqual(len([e for e in b.events if e["type"] == "data_gap"]), 1)

    def test_marktdatenunterbrechung_keine_kaeufe_bei_veralteten_daten_orders_bleiben_offen(self):
        b = self.broker(stale_sessions=3)
        limit = b.submit("A", "buy", 10, "limit", limit_price=50)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100), "B": bar(50, 51, 49, 50)})
        for i in range(1, 5):                                           # A liefert nicht mehr, B schon
            b.process_day(tag(i), {"B": bar(50, 51, 49, 50)})
        self.assertEqual(limit.status, "open")                          # keine Daten -> kein Fill, kein Verfall
        neu = b.submit("A", "buy", 5)
        self.assertEqual(neu.status, "rejected")
        self.assertIn("veraltet", neu.reason)
        self.assertEqual(b.submit("B", "buy", 5).status, "open")       # B ist aktuell
        self.assertEqual(b.pf.equity_curve[-1]["equity"], 10_000.0)     # Equity laeuft mit B-Tagen weiter, ohne A zu erfinden

    def test_dividende_und_split_ueber_den_broker(self):
        b = self.broker()
        b.submit("A", "buy", 10)
        b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
        self.assertAlmostEqual(b.on_dividend("A", 0.5, tag(1)), 5.0)
        b.on_split("A", 2.0, tag(1))
        self.assertEqual(b.pf.positions["A"].quantity, 20)


class TestNeustartUndWiederherstellung(PaperTest):
    def tage(self):
        rng = np.random.default_rng(5)
        out, p = [], 100.0
        for i in range(12):
            o = p
            c = p * (1 + rng.normal(0, 0.02))
            out.append({"A": bar(o, max(o, c) * 1.01, min(o, c) * 0.99, c)})
            p = c
        return out

    def lauf(self, b, tage, start=0):
        for i, t in enumerate(tage[start:], start):
            if i == 1:
                b.submit("A", "buy", 20, "limit", limit_price=95.0)
                b.submit("A", "buy", 5)
            if i == 4:
                b.submit("A", "sell", 5, "stop", stop_price=90.0)
            b.process_day(tag(i), t)

    def test_neustart_ergibt_exakt_denselben_verlauf_wie_durchlauf_ohne_neustart(self):
        tage = self.tage()
        with tempfile.TemporaryDirectory() as t:
            pfad = os.path.join(t, "paper.json")
            durch = self.broker()
            self.lauf(durch, tage)
            a = self.broker(state_path=pfad)
            self.lauf(a, tage[:6])                                       # offene Orders + Position existieren hier
            b = PaperBroker.load(pfad)
            self.assertEqual(len(b.open_orders()), len(a.open_orders()))
            self.assertEqual(b.pf.cash, a.pf.cash)
            self.assertEqual(b.pf.positions.keys(), a.pf.positions.keys())
            for i in range(6, 12):
                b.process_day(tag(i), tage[i])
            self.assertEqual(b.pf.cash, durch.pf.cash)
            self.assertEqual([(o.id, o.status, o.exec_price, o.quantity) for o in b.orders], [(o.id, o.status, o.exec_price, o.quantity) for o in durch.orders])
            self.assertEqual(b.pf.equity_curve, durch.pf.equity_curve)
            self.assertEqual(b.pf.trades, durch.pf.trades)
            self.assertFalse(os.path.exists(pfad + ".tmp"))              # atomar geschrieben

    def test_kaputte_hauptdatei_faellt_auf_backup_zurueck(self):
        with tempfile.TemporaryDirectory() as t:
            pfad = os.path.join(t, "paper.json")
            b = self.broker(state_path=pfad)
            b.submit("A", "buy", 5)
            b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
            b.process_day(tag(1), {"A": bar(100, 101, 99, 101)})         # zweites Speichern -> .bak = Stand nach Tag 1
            Path(pfad).write_text("{kaputt", encoding="utf-8")
            r = PaperBroker.load(pfad)
            self.assertEqual(r.last_day, tag(0))
            self.assertTrue(any(e["type"] == "restored_from_backup" for e in r.events))

    def test_nicht_wiederherstellbar_und_inkonsistent_werden_gemeldet(self):
        with tempfile.TemporaryDirectory() as t:
            pfad = os.path.join(t, "paper.json")
            with self.assertRaises(PaperStateError):
                PaperBroker.load(pfad)                                   # existiert nicht
            b = self.broker(state_path=pfad)
            b.submit("A", "buy", 5)
            b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
            st = json.loads(Path(pfad).read_text())
            st["portfolio"]["cash"] += 1000                              # Manipulation: Geld aus dem Nichts
            with self.assertRaises(PaperStateError):
                PaperBroker.from_state(st)
            st["portfolio"]["cash"] = -5.0
            with self.assertRaises(PaperStateError):
                PaperBroker.from_state(st)
            st["version"] = 99
            with self.assertRaises(PaperStateError):
                PaperBroker.from_state(st)
            with self.assertRaises(PaperStateError):
                PaperBroker.from_state({"version": 1})

    def test_journal_datei_protokolliert_ereignisse(self):
        with tempfile.TemporaryDirectory() as t:
            j = os.path.join(t, "journal.jsonl")
            b = self.broker(journal_path=j)
            b.submit("A", "buy", 5)
            b.process_day(tag(0), {"A": bar(100, 101, 99, 100)})
            zeilen = [json.loads(z) for z in Path(j).read_text().splitlines()]
            self.assertEqual([z["type"] for z in zeilen], ["order_submitted", "order_filled"])


class TestGleichheitMitBacktest(unittest.TestCase):
    def daten(self):
        return {"AAA": random_walk(220, seed=21), "BBB": random_walk(220, seed=22, price=50)}

    def paper(self, daten, trader=None, von=0, bis=None):
        t = trader
        for i, d in enumerate(sorted(daten["AAA"].index)[von:bis], von):
            bars = {s: {k: float(df.at[d, k]) for k in ("open", "high", "low", "close", "volume")} for s, df in daten.items() if d in df.index}
            t.step(d, bars)
        return t

    def test_paper_trader_und_backtest_liefern_dasselbe(self):
        daten = self.daten()
        cfg = BacktestConfig(initial_cash=50_000, position_size_pct=0.2)
        bt = BacktestEngine(daten, EmaCrossStrategy(5, 20), cfg).run()
        t = self.paper(daten, PaperTrader(PaperBroker(cfg), EmaCrossStrategy(5, 20)))
        e_bt, e_pp = bt.equity_curve["equity"].to_numpy(), t.broker.equity_frame()["equity"].to_numpy()
        np.testing.assert_allclose(e_pp, e_bt, rtol=0, atol=1e-6)
        self.assertEqual(len(t.broker.pf.trades), len(bt.trades))
        self.assertGreater(len(bt.trades), 0)
        np.testing.assert_allclose([x.pnl for x in t.broker.pf.trades], [x.pnl for x in bt.trades], atol=1e-6)
        fills_bt = [(o.symbol, o.side, str(o.exec_date), round(o.exec_price, 9), o.quantity) for o in bt.orders if o.status == "filled"]
        fills_pp = [(o.symbol, o.side, str(o.exec_date), round(o.exec_price, 9), o.quantity) for o in t.broker.orders if o.status == "filled"]
        self.assertEqual(fills_pp, fills_bt)

    def test_paper_trader_ueberlebt_neustart_mit_historie(self):
        daten = self.daten()
        cfg = BacktestConfig(initial_cash=50_000, position_size_pct=0.2)
        durch = self.paper(daten, PaperTrader(PaperBroker(cfg), EmaCrossStrategy(5, 20)))
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "p.json")
            self.paper(daten, PaperTrader(PaperBroker(cfg, state_path=pfad), EmaCrossStrategy(5, 20)), 0, 110)
            zweite = PaperTrader(PaperBroker.load(pfad), EmaCrossStrategy(5, 20))        # frischer Prozess: Zustand + Historien aus der Datei
            self.paper(daten, zweite, 110)
        np.testing.assert_allclose(zweite.broker.equity_frame()["equity"].to_numpy(), durch.broker.equity_frame()["equity"].to_numpy(), atol=1e-6)
        self.assertEqual(zweite.broker.pf.cash, durch.broker.pf.cash)


if __name__ == "__main__":
    unittest.main()
