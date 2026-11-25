"""RSI-14 mit Trendfilter: Einstieg wenn RSI < oversold UND Schlusskurs > SMA(trend_period); Ausstieg wenn RSI > overbought
ODER der Trendfilter bricht (Schlusskurs < SMA). Dazwischen: Zustand halten (NaN = keine Aenderung)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, sma, wilder_rsi


class RsiTrendStrategy(Strategy):
    name = "rsi_trend"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0, trend_period: int = 200):
        if not 0 < oversold < overbought < 100:
            raise ValueError("0 < oversold < overbought < 100 erforderlich.")
        self.period, self.oversold, self.overbought, self.trend_period = period, oversold, overbought, trend_period
        self.min_history = max(period + 1, trend_period)

    def get_parameters(self) -> dict:
        return {"period": self.period, "oversold": self.oversold, "overbought": self.overbought, "trend_period": self.trend_period}

    def generate_signals(self, history: pd.DataFrame) -> pd.Series:
        c = history["close"]
        rsi, trend = wilder_rsi(c, self.period), sma(c, self.trend_period)
        ok = trend.notna() & rsi.notna()
        rein = ok & (rsi < self.oversold) & (c > trend)
        raus = ok & ((rsi > self.overbought) | (c < trend))
        sig = pd.Series(np.nan, index=history.index)
        sig[raus] = 0.0
        sig[rein & ~raus] = 1.0
        return sig
