"""Trend-following breakout with structure and volatility gates.

Deliberately built from STRUCTURALLY INDEPENDENT confirmations rather than
a stack of oscillators. RSI, Stochastic, CCI, MACD and Williams %R are all
monotonic transforms of the same price series - requiring five of them to
agree adds lag, not evidence.

The three gates here measure different things:
  1. Direction  - Donchian breakout of the prior N-bar range (price level)
  2. Structure  - confirmed higher-highs/higher-lows (swing geometry)
  3. Trend qual - ADX above a floor (trend strength, direction-agnostic)
  4. Vol regime - ATR percentile inside a band (avoid dead and berserk tape)

Basis: time-series momentum is the single best-replicated anomaly in FX and
futures (Moskowitz, Ooi & Pedersen 2012 and successors). This is a plain
implementation of it, not a novel idea, and that is the point - novel ideas
with no out-of-sample record are how people lose money.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import indicators as ind


@dataclass(frozen=True)
class TrendBreakoutParams:
    donchian_period: int = 20
    atr_period: int = 14
    adx_period: int = 14
    adx_floor: float = 20.0
    swing_k: int = 3
    vol_lookback: int = 100
    vol_low_pct: float = 0.20
    vol_high_pct: float = 0.95
    use_structure: bool = True
    allow_shorts: bool = True


class TrendBreakout:
    def __init__(self, params: TrendBreakoutParams | None = None):
        self.p = params or TrendBreakoutParams()

    def indicators(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.p
        h, l, c = bars["high"], bars["low"], bars["close"]
        out = pd.DataFrame(index=bars.index)
        out["atr"] = ind.atr(h, l, c, p.atr_period)
        out["adx"] = ind.adx(h, l, c, p.adx_period)
        out["dc_up"], out["dc_lo"] = ind.donchian(h, l, p.donchian_period)
        out["structure"] = ind.structure_state(h, l, p.swing_k) if p.use_structure else 1.0
        # volatility regime: where does current ATR sit in its own history
        out["atr_pct"] = out["atr"].rolling(p.vol_lookback).rank(pct=True)
        return out

    def signals(self, bars: pd.DataFrame, feats: pd.DataFrame | None = None) -> pd.Series:
        p = self.p
        f = feats if feats is not None else self.indicators(bars)
        c = bars["close"]

        vol_ok = f["atr_pct"].between(p.vol_low_pct, p.vol_high_pct)
        trend_ok = f["adx"] >= p.adx_floor

        long_ok = (c > f["dc_up"]) & trend_ok & vol_ok
        short_ok = (c < f["dc_lo"]) & trend_ok & vol_ok

        if p.use_structure:
            long_ok &= f["structure"] > 0
            short_ok &= f["structure"] < 0
        if not p.allow_shorts:
            short_ok &= False

        sig = pd.Series(0.0, index=bars.index)
        sig[long_ok.fillna(False)] = 1.0
        sig[short_ok.fillna(False)] = -1.0
        return sig
