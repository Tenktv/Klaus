"""Zeitlich saubere Validierung: Training / Validation / Out-of-Sample und Walk-Forward. Keine zufaellige Vermischung.

Regeln gegen Data Leakage:
- Parameter werden NUR mit Daten VOR dem Testfenster gewaehlt (Training; optional Validation zur Auswahl) - das Testfenster wird
  genau einmal mit den gewaehlten Parametern gefahren und nie zur Optimierung benutzt.
- Fuer Indikator-Warmup duerfen Kerzen VOR dem Fenster als Historie dienen (nur Vergangenheit); gehandelt und bewertet wird nur im Fenster.
- Jede Periode wird separat ausgegeben, inkl. der genutzten Datenbereiche."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import pandas as pd

from .backtest import BacktestEngine
from .config import BacktestConfig, RiskConfig


@dataclass(frozen=True)
class Split:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


def time_split(index: pd.DatetimeIndex, train: float = 0.6, validation: float = 0.2) -> dict[str, Split]:
    """Chronologisch: Training | Validation | Out-of-Sample (Rest). Anteile nach Anzahl Handelstage."""
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("Index muss streng aufsteigend sein.")
    if train <= 0 or validation < 0 or train + validation >= 1:
        raise ValueError("train + validation muss < 1 sein (Rest ist Out-of-Sample).")
    n = len(index)
    a, b = int(n * train), int(n * (train + validation))
    if a < 1 or b <= a - (1 if validation == 0 else 0) or n - b < 1:
        raise ValueError("Zu wenig Daten fuer diese Aufteilung.")
    out = {"train": Split("train", index[0], index[a - 1])}
    if validation > 0:
        out["validation"] = Split("validation", index[a], index[b - 1])
    out["out_of_sample"] = Split("out_of_sample", index[b], index[-1])
    return out


def walk_forward_windows(index: pd.DatetimeIndex, train_len: int, test_len: int, step: int | None = None) -> list[dict]:
    """Rollierende Fenster in Handelstagen: [train_len Tage Training][test_len Tage Test], weiter um step (Standard test_len)."""
    step = step or test_len
    if min(train_len, test_len, step) < 1:
        raise ValueError("Fensterlaengen muessen >= 1 sein.")
    fenster, i = [], 0
    while i + train_len + test_len <= len(index):
        fenster.append({"train": Split("train", index[i], index[i + train_len - 1]),
                        "test": Split("test", index[i + train_len], index[i + train_len + test_len - 1])})
        i += step
    return fenster


def _score(metrics: dict, ziel: str) -> float:
    v = metrics.get(ziel)
    return float("-inf") if v is None else float(v)


def walk_forward(data: dict[str, pd.DataFrame], strategy_factory, param_grid: dict[str, list], train_len: int, test_len: int, step: int | None = None,
                 config: BacktestConfig | None = None, risk: RiskConfig | None = None, objective: str = "net_return", warmup: int = 0, **engine_kw) -> list[dict]:
    """Je Fenster: beste Parameter auf dem Training waehlen (objective), dann Testfenster genau einmal mit diesen Parametern fahren.
    warmup: zusaetzliche Kerzen VOR dem Fenster als Indikator-Historie (nur Vergangenheit)."""
    union = sorted(set().union(*[set(d.index) for d in data.values()]))
    idx = pd.DatetimeIndex(union)
    namen = list(param_grid)
    kombis = [dict(zip(namen, v)) for v in itertools.product(*[param_grid[n] for n in namen])]
    ergebnisse = []
    for w in walk_forward_windows(idx, train_len, test_len, step):
        tr, te = w["train"], w["test"]
        pos0 = idx.get_loc(tr.start)
        start_hist = idx[max(0, pos0 - warmup)]
        beste, bester_wert = None, float("-inf")
        for p in kombis:
            slice_tr = {s: d[(d.index >= start_hist) & (d.index <= tr.end)] for s, d in data.items()}
            try:
                r = BacktestEngine(slice_tr, strategy_factory(**p), config, risk, **engine_kw).run(trade_start=tr.start)
            except Exception:   # ungueltige Parameter/zu wenig Daten in diesem Fenster -> Kombination ueberspringen
                continue
            wert = _score(r.metrics, objective)
            if wert > bester_wert:
                beste, bester_wert = p, wert
        if beste is None:
            ergebnisse.append({"train": tr, "test": te, "params": None, "train_score": None, "test_metrics": None, "note": "keine gueltige Parameterkombination"})
            continue
        pos_te = idx.get_loc(te.start)
        start_te = idx[max(0, pos_te - warmup)]   # Warmup nur aus Daten VOR dem Testfenster
        slice_te = {s: d[(d.index >= start_te) & (d.index <= te.end)] for s, d in data.items()}
        r = BacktestEngine(slice_te, strategy_factory(**beste), config, risk, **engine_kw).run(trade_start=te.start)
        ergebnisse.append({"train": tr, "test": te, "params": beste, "train_score": bester_wert, "test_metrics": r.metrics,
                           "data_used": {"train": (str(start_hist.date()), str(tr.end.date())), "test": (str(start_te.date()), str(te.end.date()))}})
    return ergebnisse
