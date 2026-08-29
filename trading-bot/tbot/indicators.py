"""Causal indicators.

Every function here returns a series aligned to the input index where the
value at position i uses ONLY data at positions <= i. Anything needing
future bars (swing confirmation) returns the value at its *confirmation*
bar, not at the bar it describes. That distinction is the difference
between a backtest and a fantasy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's ATR (RMA smoothing)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's ADX - trend strength, direction-agnostic."""
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    alpha = 1.0 / period
    tr_rma = true_range(high, low, close).ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(
        alpha=alpha, adjust=False, min_periods=period).mean() / tr_rma
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(
        alpha=alpha, adjust=False, min_periods=period).mean() / tr_rma

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def donchian(high: pd.Series, low: pd.Series, period: int = 20):
    """Prior-N-bar channel, EXCLUDING the current bar.

    Excluding the current bar matters: including it makes a breakout
    detectable on the same bar that creates it, which is not tradeable.
    """
    upper = high.rolling(period).max().shift(1)
    lower = low.rolling(period).min().shift(1)
    return upper, lower


def realized_vol(close: pd.Series, period: int = 20) -> pd.Series:
    return close.pct_change().rolling(period).std()


def swing_points(high: pd.Series, low: pd.Series, k: int = 3):
    """Fractal swing highs/lows, reported at their CONFIRMATION bar.

    A swing high at bar i requires k bars on each side to be lower. That
    fact is only knowable at bar i+k. This returns two frames whose index
    position i holds the most recent swing *confirmed as of* bar i, along
    with the bar it actually occurred on.

    Naive implementations centre the window and leave the value at bar i,
    which leaks k bars of future data into every signal. That single bug
    is responsible for a large share of "profitable" retail backtests.
    """
    n = len(high)
    hv, lv = high.to_numpy(), low.to_numpy()

    swing_hi = np.full(n, np.nan)
    swing_lo = np.full(n, np.nan)
    swing_hi_at = np.full(n, -1, dtype=np.int64)
    swing_lo_at = np.full(n, -1, dtype=np.int64)

    last_hi = np.nan; last_hi_at = -1
    last_lo = np.nan; last_lo_at = -1

    for i in range(n):
        c = i - k  # candidate bar, now fully surrounded
        if c - k >= 0:
            window_h = hv[c - k:c + k + 1]
            if hv[c] == window_h.max() and np.argmax(window_h) == k:
                last_hi, last_hi_at = hv[c], c
            window_l = lv[c - k:c + k + 1]
            if lv[c] == window_l.min() and np.argmin(window_l) == k:
                last_lo, last_lo_at = lv[c], c
        swing_hi[i], swing_hi_at[i] = last_hi, last_hi_at
        swing_lo[i], swing_lo_at[i] = last_lo, last_lo_at

    return (
        pd.DataFrame({"level": swing_hi, "bar": swing_hi_at}, index=high.index),
        pd.DataFrame({"level": swing_lo, "bar": swing_lo_at}, index=low.index),
    )


def structure_state(high: pd.Series, low: pd.Series, k: int = 3) -> pd.Series:
    """+1 when the last two confirmed swings are HH and HL, -1 for LH/LL, else 0.

    This is the market-structure filter: 'is each pullback low higher than
    the one before it'. Uses confirmed swings only, so it lags - correctly.
    """
    hi, lo = swing_points(high, low, k)
    n = len(high)
    hv, lv = hi["level"].to_numpy(), lo["level"].to_numpy()
    hb, lb = hi["bar"].to_numpy(), lo["bar"].to_numpy()

    prev_hi = np.full(n, np.nan)
    prev_lo = np.full(n, np.nan)
    ph = pl = np.nan
    last_hb = last_lb = -1
    for i in range(n):
        if hb[i] != last_hb and last_hb != -1:
            ph = hv[i - 1] if i > 0 else np.nan
        if lb[i] != last_lb and last_lb != -1:
            pl = lv[i - 1] if i > 0 else np.nan
        prev_hi[i], prev_lo[i] = ph, pl
        last_hb, last_lb = hb[i], lb[i]

    out = np.zeros(n)
    up = (hv > prev_hi) & (lv > prev_lo)
    dn = (hv < prev_hi) & (lv < prev_lo)
    out[up] = 1.0
    out[dn] = -1.0
    return pd.Series(out, index=high.index, name="structure")
