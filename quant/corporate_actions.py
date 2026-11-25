"""Dividenden und Aktiensplits als echte Ereignisse (nicht ueber Adjusted Close).

Konventionen (wichtig):
- Preise im Backtest sind ROH (so gehandelt). Splits werden als Ereignis verbucht: Stueckzahl * ratio, Einstandskurs / ratio.
- Dividende je Aktie wird am Ex-Tag als Cash gebucht - nur fuer Stuecke, die am Vorabend schon gehalten wurden
  (wer am Ex-Tag zum Open kauft, bekommt nichts). Zahltag wird nicht modelliert (Vereinfachung).
- Adjusted Close wird NIE als Ausfuehrungspreis benutzt und Dividenden werden nie doppelt (Cash + angepasster Kurs) gerechnet.
- Quellen, deren "rohe" Kurse schon splitbereinigt sind (z. B. Yahoo mit auto_adjust=False), setzen prices_split_adjusted=True;
  dann werden Splits NICHT nochmal auf die Position angewendet."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class CorporateActions:
    dividends: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))   # Ex-Datum -> Betrag je Aktie
    splits: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))      # Ex-Datum -> Verhaeltnis (2.0 = 2:1)
    prices_split_adjusted: bool = False

    def __post_init__(self):
        self.dividends = self._norm(self.dividends, "Dividende", positiv=True)
        self.splits = self._norm(self.splits, "Split", positiv=True)

    @staticmethod
    def _norm(s: pd.Series, name: str, positiv: bool) -> pd.Series:
        if s is None or len(s) == 0:
            return pd.Series(dtype=float)
        s = pd.Series(s, dtype=float)
        idx = pd.to_datetime(s.index)
        s.index = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
        if s.index.has_duplicates:
            raise ValueError(f"{name}: doppeltes Ex-Datum.")
        if (s <= 0).any() or s.isna().any():
            raise ValueError(f"{name}: Werte muessen > 0 sein.")
        return s.sort_index()

    @classmethod
    def from_dict(cls, d: dict | None, **kw) -> "CorporateActions":
        d = d or {}
        return cls(pd.Series(d.get("dividends", {}), dtype=float), pd.Series(d.get("splits", {}), dtype=float), **kw)
