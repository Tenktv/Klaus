"""Beispiel: Backtest auf KUENSTLICHEN Zufallsdaten (nur zum Ausprobieren der API - die Zahlen sagen nichts ueber echte Maerkte).

    python -m quant.example"""
import numpy as np
import pandas as pd

from quant.backtest import BacktestEngine
from quant.config import BacktestConfig, RiskConfig
from quant.strategies import EmaCrossStrategy


def kuenstliche_kerzen(n=500, seed=1, preis=100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = preis * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    o = np.concatenate([[preis], c[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.004, "low": np.minimum(o, c) * 0.996, "close": c, "volume": 1e6},
                        index=pd.bdate_range("2022-01-03", periods=n))


if __name__ == "__main__":
    daten = {"AAA": kuenstliche_kerzen(seed=1), "BBB": kuenstliche_kerzen(seed=2), "SPY": kuenstliche_kerzen(seed=3)}
    r = BacktestEngine(daten, EmaCrossStrategy(20, 50), BacktestConfig(benchmark="SPY"), risk=RiskConfig.beispiel_test()).run()
    print("KUENSTLICHE DATEN - keine Aussage ueber reale Performance")
    for k in ("net_return", "max_drawdown", "sharpe", "number_of_trades", "win_rate", "fees", "benchmark_return"):
        print(f"{k:18}", r.metrics.get(k))
