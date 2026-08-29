"""Synthetic price generators - used to validate the ENGINE, not strategies.

A random walk contains no exploitable structure by construction. Any
backtest harness that shows profit on one (beyond noise, before costs) has
a look-ahead bug. This is the null hypothesis the engine must fail to beat.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def random_walk_ohlc(
    n: int = 20_000, s0: float = 1.1000, vol: float = 0.0006,
    drift: float = 0.0, seed: int = 0, freq: str = "1h",
) -> pd.DataFrame:
    """Driftless GBM sampled into OHLC bars. No structure, no edge."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, size=(n, 4))
    close = s0 * np.exp(np.cumsum(steps[:, 0]))
    open_ = np.concatenate([[s0], close[:-1]])
    # intrabar extremes drawn around the open/close path
    spread = np.abs(rng.normal(0, vol, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    idx = pd.date_range("2020-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=idx
    )


def trending_ohlc(n: int = 20_000, s0: float = 1.10, vol: float = 0.0006,
                  regime_len: int = 500, strength: float = 0.35,
                  seed: int = 0, freq: str = "1h") -> pd.DataFrame:
    """Alternating persistent up/down regimes - contains a REAL trend edge.

    Used as a positive control: a trend-following engine that cannot make
    money here is broken in the opposite direction.
    """
    rng = np.random.default_rng(seed)
    n_reg = n // regime_len + 1
    signs = rng.choice([-1.0, 1.0], size=n_reg)
    drift = np.repeat(signs, regime_len)[:n] * vol * strength
    rets = rng.normal(drift, vol)
    close = s0 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[s0], close[:-1]])
    spread = np.abs(rng.normal(0, vol, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    idx = pd.date_range("2020-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)
