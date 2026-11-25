"""Strategie-Basisklasse. Vertrag (verpflichtend, wird getestet):

- generate_signals(history) -> Series gleicher Laenge: gewuenschter Zustand NACH Abschluss der jeweiligen Kerze
    1.0 = long sein, 0.0 = flach sein, NaN = nichts aendern. Der Wert in Zeile t darf NUR von Zeilen <= t abhaengen
    (kein Look-ahead). Die Engine fuehrt die daraus entstehende Order fruehestens zum Open der naechsten Kerze aus.
- update(history) -> Signal der LETZTEN (abgeschlossenen) Kerze; die Engine ruft es je Kerze mit history[:t+1] auf.
- initialize() setzt internen Zustand zurueck (die Engine arbeitet je Symbol mit einer eigenen Kopie).
- get_parameters() liefert die Konfiguration (fuer Protokoll/Dashboard/Walk-Forward).
history: DataFrame mit rohen/signalbereinigten OHLCV-Spalten open, high, low, close, volume (nie adj_close)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Strategy(ABC):
    name = "strategy"
    min_history = 1

    def initialize(self) -> None:
        """Zustand zuruecksetzen (Standard: zustandslos)."""

    @abstractmethod
    def get_parameters(self) -> dict: ...

    @abstractmethod
    def generate_signals(self, history: pd.DataFrame) -> pd.Series: ...

    def update(self, history: pd.DataFrame) -> float:
        if len(history) < self.min_history:
            return float("nan")
        return float(self.generate_signals(history).iloc[-1])

    def describe(self) -> str:
        return f"{self.name} {self.get_parameters()}"


def ema(x: pd.Series, n: int) -> pd.Series:
    """Exponentieller Durchschnitt (adjust=False, min_periods=n): erster Wert nach n Beobachtungen, danach rekursiv - nur Vergangenheit."""
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def wilder_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI nach Wilder (Glaettung alpha=1/n). avg_loss = 0 -> RSI 100 (bei avg_gain = 0 ebenfalls: 50). Erste n Werte NaN."""
    d = close.diff()
    auf, ab = d.clip(lower=0.0), (-d).clip(lower=0.0)
    ag = auf.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    al = ab.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rsi = 100.0 - 100.0 / (1.0 + ag / al.replace(0.0, np.nan))
    rsi = rsi.where(~((al == 0) & (ag > 0)), 100.0)
    rsi = rsi.where(~((al == 0) & (ag == 0)), 50.0)
    return rsi.where(ag.notna() & al.notna())
