"""Gemeinsame Hilfen fuer die quant-Tests: kuenstliche Kursdaten und eine geskriptete Strategie."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from quant.strategies.base import Strategy  # noqa: E402


def frame(opens, closes, start="2024-01-01", highs=None, lows=None, volume=1_000_000, dates=None):
    """Kerzen aus Open/Close; High/Low werden gueltig dazu gebaut (+/- 0,5)."""
    n = len(opens)
    idx = pd.DatetimeIndex(dates) if dates is not None else pd.bdate_range(start, periods=n)
    o, c = np.array(opens, dtype=float), np.array(closes, dtype=float)
    h = np.array(highs, dtype=float) if highs is not None else np.maximum(o, c) + 0.5
    l = np.array(lows, dtype=float) if lows is not None else np.minimum(o, c) - 0.5
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": float(volume)}, index=idx)


class Scripted(Strategy):
    """Signal je Kerzendatum vorgegeben: {"2024-01-01": 1.0, ...}; sonst NaN. Merkt sich, welche Historie sie gesehen hat."""
    name = "scripted"

    def __init__(self, script):
        self.script = {pd.Timestamp(k): float(v) for k, v in script.items()}
        self.seen_last = []

    def initialize(self):
        self.seen_last = []

    def get_parameters(self):
        return {"script": {str(k.date()): v for k, v in self.script.items()}}

    def generate_signals(self, history):
        return pd.Series([self.script.get(t, np.nan) for t in history.index], index=history.index)

    def update(self, history):
        self.seen_last.append(history.index[-1])
        return float(self.generate_signals(history).iloc[-1])


def random_walk(n=300, seed=1, start="2023-01-02", drift=0.0005, vol=0.01, price=100.0):
    rng = np.random.default_rng(seed)
    c = price * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    o = np.concatenate([[price], c[:-1]]) * (1 + rng.normal(0, 0.002, n))
    h = np.maximum(o, c) * 1.005
    l = np.minimum(o, c) * 0.995
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e6}, index=pd.bdate_range(start, periods=n))
