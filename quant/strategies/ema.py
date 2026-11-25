"""EMA-Trendfolge (Standard 20/50): long, solange EMA(schnell) > EMA(langsam) auf dem Schlusskurs der abgeschlossenen Kerze."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, ema


class EmaCrossStrategy(Strategy):
    name = "ema_cross"

    def __init__(self, fast: int = 20, slow: int = 50):
        if not 1 <= fast < slow:
            raise ValueError("fast muss kleiner als slow sein.")
        self.fast, self.slow = fast, slow
        self.min_history = slow

    def get_parameters(self) -> dict:
        return {"fast": self.fast, "slow": self.slow}

    def generate_signals(self, history: pd.DataFrame) -> pd.Series:
        c = history["close"]
        f, s = ema(c, self.fast), ema(c, self.slow)
        sig = pd.Series(np.where(f > s, 1.0, 0.0), index=history.index)
        return sig.where(f.notna() & s.notna())
