"""Kennzahlen. Definitionen (alle auf Tages-Equity bezogen, periods_per_year = 252):

- Renditen r_t = equity_t / equity_(t-1) - 1 (einfache Tagesrenditen, aus der Equity-Kurve; erste Zeile hat keine Rendite).
- net_return    = equity_ende / startkapital - 1 (nach Gebuehren und Slippage, inkl. Dividenden).
- total_return  = (equity_ende + gebuehren) / startkapital - 1 (VOR expliziten Gebuehren; Slippage steckt in den Preisen).
- annualized_return = (equity_ende / startkapital) ** (periods_per_year / n_renditen) - 1; None bei < 2 Beobachtungen.
- volatility    = std(r, ddof=1) * sqrt(periods_per_year); None bei < 2 Renditen. portfolio_volatility = identisch (Portfolio-Equity).
- sharpe        = mean(r - rf_t) / std(r, ddof=1) * sqrt(periods_per_year), rf_t = rf / periods_per_year; None wenn std = 0 oder < 2 Renditen.
- sortino       = mean(r - rf_t) / downside_dev * sqrt(periods_per_year), downside_dev = sqrt(mean(min(r - rf_t, 0)^2)) ueber ALLE Beobachtungen;
                  None wenn keine Abwaerts-Beobachtung (undefiniert).
- max_drawdown  = min(equity / laufendes_Maximum - 1) (negativ, 0 wenn nie ein Rueckgang). average_drawdown = Mittel der negativen Drawdown-Werte (0 ohne).
- Trades zaehlen abgeschlossene Verkaeufe (auch Teilverkaeufe). win = pnl > 0, loss = pnl < 0 (netto inkl. Gebuehren).
  win_rate = wins/trades (None ohne Trades). profit_factor = Summe Gewinne / |Summe Verluste| (None, wenn es keine Verluste gibt - undefiniert).
  average_win/average_loss = Mittel der Gewinn-/Verlust-Trades (loss negativ; None, wenn es keine gibt). average_holding_days = Mittel der Haltetage.
- exposure = Mittel(invested/equity) ueber alle Tage; cash_pct = Mittel(cash/equity); invested_capital = investiertes Kapital am letzten Tag."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .portfolio import Portfolio


def _none(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def daily_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def sharpe_ratio(r: pd.Series, rf_annual: float = 0.0, ppy: int = 252):
    if len(r) < 2:
        return None
    ex = r - rf_annual / ppy
    sd = r.std(ddof=1)
    if not math.isfinite(sd) or sd < 1e-15:
        return None
    return float(ex.mean() / sd * math.sqrt(ppy))


def sortino_ratio(r: pd.Series, rf_annual: float = 0.0, ppy: int = 252):
    if len(r) < 2:
        return None
    ex = r - rf_annual / ppy
    dd = math.sqrt(float((np.minimum(ex, 0.0) ** 2).mean()))
    if dd < 1e-15:
        return None
    return float(ex.mean() / dd * math.sqrt(ppy))


def trade_stats(trades) -> dict:
    pnls = [t.pnl for t in trades]
    gewinne, verluste = [p for p in pnls if p > 0], [p for p in pnls if p < 0]
    return {
        "number_of_trades": len(pnls), "winning_trades": len(gewinne), "losing_trades": len(verluste),
        "win_rate": len(gewinne) / len(pnls) if pnls else None,
        "profit_factor": sum(gewinne) / abs(sum(verluste)) if verluste else None,
        "average_win": float(np.mean(gewinne)) if gewinne else None,
        "average_loss": float(np.mean(verluste)) if verluste else None,
        "average_holding_days": float(np.mean([t.holding_days for t in trades])) if trades else None,
    }


def compute_metrics(equity_curve: pd.DataFrame, pf: Portfolio, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> dict:
    eq = equity_curve["equity"]
    r = daily_returns(eq)
    e0, e1 = pf.initial_cash, float(eq.iloc[-1])
    dd = drawdown_series(eq)
    neg = dd[dd < 0]
    vol = float(r.std(ddof=1) * math.sqrt(periods_per_year)) if len(r) >= 2 else None
    m = {
        "start_equity": e0, "end_equity": e1,
        "net_return": e1 / e0 - 1, "total_return": (e1 + pf.fees_total) / e0 - 1,
        "annualized_return": float((e1 / e0) ** (periods_per_year / len(r)) - 1) if len(r) >= 2 and e1 > 0 else None,
        "realized_pnl": pf.realized_pnl, "unrealized_pnl": pf.unrealized_pnl, "dividends": pf.dividends_total,
        "fees": pf.fees_total, "slippage_cost": pf.slippage_total,
        "max_drawdown": float(dd.min()) if len(dd) else 0.0, "average_drawdown": float(neg.mean()) if len(neg) else 0.0,
        "volatility": _none(vol), "portfolio_volatility": _none(vol),
        "sharpe": sharpe_ratio(r, risk_free_rate, periods_per_year), "sortino": sortino_ratio(r, risk_free_rate, periods_per_year),
        "exposure": float((equity_curve["invested"] / eq).mean()), "cash_pct": float((equity_curve["cash"] / eq).mean()),
        "invested_capital": float(equity_curve["invested"].iloc[-1]), "observations": int(len(r)),
    }
    m.update(trade_stats(pf.trades))
    return m
