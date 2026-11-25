"""Event-basierte Backtest-Engine (Tagesdaten, Long-only, deterministisch).

Ablauf je Handelstag d (Vereinigung aller Symbolkalender, aufsteigend):
  1. Corporate Actions mit Ex-Datum d (Split, dann Dividende) - auf Positionen vom Vorabend.
  2. Orders aus Signalen des Vortags (bzw. der letzten Kerze des Symbols) werden zum OPEN von d ausgefuehrt:
     erst Verkaeufe, dann Kaeufe, je alphabetisch nach Symbol. Hat ein Symbol an d keine Kerze, bleibt seine Order bis zur naechsten Kerze offen.
  3. Bewertung zum Schlusskurs von d (Symbole ohne Kerze: letzter bekannter Schlusskurs), Equity-Zeile.
  4. Strategien sehen die abgeschlossenen Kerzen bis einschliesslich d und erzeugen Signale -> Orders fuer die NAECHSTE Kerze.
Modellannahme (keine Garantie fuer reale Ausfuehrung): Fill zum rohen Open der Folgekerze, +/- Slippage, plus Gebuehr je Orderseite.
Signale der letzten Kerze werden nie ausgefuehrt (verfallen, mit Status "expired" protokolliert)."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import pandas as pd

from .config import MARKETS, BacktestConfig, MarketConfig, RiskConfig
from .corporate_actions import CorporateActions
from .data import DataError, ValidationReport, validate_ohlcv
from .metrics import compute_metrics
from .portfolio import InsufficientCash, Order, Portfolio, PortfolioError
from .risk import RiskManager
from .strategies.base import Strategy

OHLC = ["open", "high", "low", "close"]


@dataclass
class BacktestResult:
    config: BacktestConfig
    portfolio: Portfolio
    equity_curve: pd.DataFrame
    orders: list
    signals: list
    metrics: dict
    benchmark: pd.DataFrame | None
    reports: dict
    risk_config: RiskConfig

    @property
    def trades(self):
        return self.portfolio.trades

    @property
    def rejected_orders(self):
        return [o for o in self.orders if o.status == "rejected"]

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ | {"return_pct": t.return_pct} for t in self.trades])

    def orders_frame(self) -> pd.DataFrame:
        return pd.DataFrame([o.__dict__ for o in self.orders])

    def monthly_returns(self) -> pd.Series:
        eq = self.equity_curve["equity"]
        m = eq.resample("ME").last()
        start = pd.Series([self.portfolio.initial_cash], index=[eq.index[0] - pd.Timedelta(days=1)])
        return pd.concat([start, m]).pct_change().dropna()


class BacktestEngine:
    def __init__(self, data: dict[str, pd.DataFrame], strategy: Strategy | dict[str, Strategy], config: BacktestConfig | None = None,
                 risk: RiskConfig | None = None, actions: dict[str, CorporateActions] | None = None,
                 symbol_markets: dict[str, str] | None = None, validate: bool = True):
        self.config = config or BacktestConfig()
        self.risk_config = risk or RiskConfig()
        self.risk = RiskManager(self.risk_config)
        if not data:
            raise DataError("Keine Daten.")
        self.symbol_markets = {s: (symbol_markets or {}).get(s, "equity") for s in data}
        self.markets: dict[str, MarketConfig] = {}
        for s, m in self.symbol_markets.items():
            if m not in MARKETS:
                raise ValueError(f"Unbekannter Markt {m!r} fuer {s}.")
            if not MARKETS[m].enabled:
                raise ValueError(f"Markt {m!r} ({s}) ist noch nicht freigeschaltet: {MARKETS[m].note}")
            self.markets[s] = MARKETS[m]
        self.data, self.reports = {}, {}
        for s in sorted(data):
            if validate:
                self.data[s], self.reports[s] = validate_ohlcv(data[s], s, self.markets[s])
            else:
                self.data[s], self.reports[s] = data[s], ValidationReport(s, len(data[s]), len(data[s]))
        self.actions = {s: (actions or {}).get(s, CorporateActions()) for s in self.data}
        self.strategies = {s: copy.deepcopy(strategy[s] if isinstance(strategy, dict) else strategy) for s in self.data
                           if not isinstance(strategy, dict) or s in strategy}
        if not self.strategies:
            raise ValueError("Keine Strategie zugeordnet.")
        if self.config.benchmark and self.config.benchmark not in self.data:
            raise ValueError("Benchmark-Symbol nicht im Datensatz.")

    def _rates(self, s: str) -> tuple[float, float, bool]:
        m = self.markets[s]
        return (self.config.fee_rate if m.fee_rate is None else m.fee_rate, self.config.slippage_rate if m.slippage_rate is None else m.slippage_rate,
                self.config.allow_fractional if m.allow_fractional is None else m.allow_fractional)

    def run(self, trade_start=None, trade_end=None) -> BacktestResult:
        """trade_start/trade_end: nur in diesem Fenster wird gehandelt und bewertet; davor liegende Kerzen dienen als Warmup fuer Indikatoren."""
        cfg = self.config
        dates = sorted(set().union(*[set(d.index) for d in self.data.values()]))
        ts = pd.Timestamp(trade_start) if trade_start is not None else dates[0]
        te = pd.Timestamp(trade_end) if trade_end is not None else dates[-1]
        dates = [d for d in dates if d <= te]
        pf = Portfolio(cfg.initial_cash)
        for s, st in self.strategies.items():
            st.initialize()
        pos_idx = {s: 0 for s in self.data}                 # Anzahl bereits gesehener Kerzen je Symbol
        sig_data = {s: d.copy() for s, d in self.data.items()}   # signalbereinigte Historie (Splits kausal eingearbeitet)
        last_close: dict[str, float] = {}
        pending: dict[str, Order] = {}
        orders: list[Order] = []
        signals: list[dict] = []
        peak = cfg.initial_cash
        oid = 0
        done_div: dict[str, set] = {s: set() for s in self.data}
        done_split: dict[str, set] = {s: set() for s in self.data}

        def naechste_kerze(sym, nach):
            idx = self.data[sym].index
            i = idx.searchsorted(nach, side="right")
            return idx[i] if i < len(idx) else None

        for d in dates:
            heute = d.date()
            # --- 1. Corporate Actions ---------------------------------------------------------------------------
            for s in sorted(self.data):
                a = self.actions[s]
                for ex, ratio in a.splits.items():
                    if ex <= d and ex not in done_split[s]:
                        done_split[s].add(ex)
                        if not a.prices_split_adjusted:
                            pf.apply_split(s, float(ratio), ex.date())
                            if s in last_close:
                                last_close[s] /= ratio
                            n = int(sig_data[s].index.searchsorted(ex, side="left"))   # Kerzen VOR dem Ex-Tag auf neues Niveau bringen
                            sig_data[s].iloc[:n, sig_data[s].columns.get_indexer(OHLC)] /= ratio
                            sig_data[s].iloc[:n, sig_data[s].columns.get_loc("volume")] *= ratio
                for ex, div in a.dividends.items():
                    if ex <= d and ex not in done_div[s]:
                        done_div[s].add(ex)
                        pf.apply_dividend(s, float(div), ex.date())
            # --- 2. Ausfuehrung zum Open ------------------------------------------------------------------------
            heute_open = {s: float(self.data[s].at[d, "open"]) for s in self.data if d in self.data[s].index}
            marks = {**last_close, **heute_open}
            ausfuehren = sorted((o for o in pending.values() if o.symbol in heute_open and (trade_start is None or d >= ts)), key=lambda o: (o.side != "sell", o.symbol))
            for o in ausfuehren:
                del pending[o.symbol]
                fee_r, slip_r, frac = self._rates(o.symbol)
                op = heute_open[o.symbol]
                o.exec_date, o.ref_open = heute, op
                if o.side == "sell":
                    p = pf.positions.get(o.symbol)
                    if p is None:
                        o.status, o.reason = "rejected", "Keine Position zum Verkaufen (Long-only)."
                        continue
                    preis = op * (1 - slip_r)
                    qty = p.quantity
                    fee = qty * preis * fee_r
                    pf.sell(o.symbol, qty, preis, fee, heute, qty * (op - preis))
                    o.quantity, o.exec_price, o.fee, o.slippage_cost, o.status = qty, preis, fee, qty * (op - preis), "filled"
                else:
                    preis = op * (1 + slip_r)
                    eq = pf.equity(marks)
                    ziel = cfg.position_size_pct * eq
                    ziel = min(ziel, self.risk.max_buy_value(pf, o.symbol, marks, peak))
                    qty = ziel / (preis * (1 + fee_r))
                    qty = qty if frac else math.floor(qty + 1e-12)
                    if qty <= 0:
                        o.status, o.reason, o.quantity = "rejected", "Ordergroesse 0 (Risikogrenzen, Cash oder Kurs zu hoch).", 0.0
                        continue
                    fee = qty * preis * fee_r
                    dec = self.risk.check_buy(pf, o.symbol, qty, preis, fee, marks, peak)
                    o.quantity = qty
                    if not dec.approved:
                        o.status, o.reason = "rejected", " ".join(dec.reasons)
                        continue
                    try:
                        pf.buy(o.symbol, qty, preis, fee, heute, qty * (preis - op))
                    except InsufficientCash as e:
                        o.status, o.reason = "rejected", str(e)
                        continue
                    o.exec_price, o.fee, o.slippage_cost, o.status = preis, fee, qty * (preis - op), "filled"
            # --- 3. Bewertung zum Schluss -----------------------------------------------------------------------
            for s in self.data:
                if d in self.data[s].index:
                    last_close[s] = float(self.data[s].at[d, "close"])
                    pos_idx[s] = int(self.data[s].index.get_loc(d)) + 1
            pf.mark(last_close)
            in_fenster = d >= ts
            if in_fenster:
                row = pf.record(heute)
                peak = max(peak, row["equity"])
            # --- 4. Signale (nur abgeschlossene Kerzen bis d) ---------------------------------------------------
            if in_fenster:
                for s in sorted(self.strategies):
                    if d not in self.data[s].index:
                        continue
                    hist = sig_data[s].iloc[: pos_idx[s]]
                    assert hist.index[-1] == d, "Look-ahead-Schutz: Historie muss mit der aktuellen Kerze enden."
                    st = self.strategies[s]
                    sig = st.update(hist)
                    nxt = naechste_kerze(s, d)
                    aktion = "none"
                    if not math.isnan(sig):
                        if sig >= 0.5 and s not in pf.positions and s not in pending:
                            aktion = "buy"
                        elif sig < 0.5 and s in pf.positions and s not in pending:
                            aktion = "sell"
                    signals.append({"symbol": s, "candle_date": heute, "signal": None if math.isnan(sig) else sig, "action": aktion,
                                    "execute_not_before": nxt.date() if nxt is not None else None, "strategy": st.name})
                    if aktion != "none":
                        oid += 1
                        o = Order(oid, s, aktion, heute, st.name)
                        orders.append(o)
                        if nxt is None:
                            o.status, o.reason = "expired", "Keine weitere Kerze: Signal der letzten Kerze wird nicht ausgefuehrt."
                        else:
                            pending[s] = o
        for o in pending.values():
            o.status, o.reason = "expired", "Backtest-Ende vor Ausfuehrung."
        eqc = pd.DataFrame(pf.equity_curve)
        if eqc.empty:
            raise DataError("Kein Handelstag im Fenster.")
        eqc["date"] = pd.to_datetime(eqc["date"])
        eqc = eqc.set_index("date")
        metrics = compute_metrics(eqc, pf, cfg.risk_free_rate, cfg.periods_per_year)
        bench = self._benchmark(eqc) if cfg.benchmark else None
        if bench is not None:
            metrics["benchmark_return"] = float(bench["equity"].iloc[-1] / bench["equity"].iloc[0] - 1)
        return BacktestResult(cfg, pf, eqc, orders, signals, metrics, bench, self.reports, self.risk_config)

    def _benchmark(self, eqc: pd.DataFrame) -> pd.DataFrame:
        """Kaufen+Halten des Benchmark-Symbols (roher Schluss, ohne Kosten/Dividenden), skaliert auf das Startkapital."""
        c = self.data[self.config.benchmark]["close"].reindex(eqc.index).ffill()
        c = c.dropna()
        return pd.DataFrame({"equity": self.config.initial_cash * c / c.iloc[0]})
