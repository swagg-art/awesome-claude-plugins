"""Mean-reversion fade, for markets whose variance ratio is below 1.

Motivated by measurement, not preference: the variance-ratio test on
EURUSD 2024 rejects the random walk in the MEAN-REVERTING direction at
q=2, 4 and 64. A breakout system is the wrong shape for that tape.

Entry: price stretched beyond z_entry standard deviations from its own
moving average, in the direction of reversion. Optional regime gate
requiring ADX to be LOW (no strong trend to be run over by).

Note on payoff geometry: mean reversion earns a high win rate at a
reward:risk below 1. That is the honest shape of the trade - a system
with 65% wins at 0.7 RRR is not worse than 35% wins at 2.0 RRR, and
insisting on a 2:1 payoff here would break the strategy on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import indicators as ind


@dataclass(frozen=True)
class MeanReversionParams:
    ma_period: int = 50
    z_entry: float = 2.0
    atr_period: int = 14
    adx_period: int = 14
    adx_ceiling: float = 30.0     # skip when a strong trend is running
    use_adx_gate: bool = True
    allow_shorts: bool = True


class MeanReversion:
    def __init__(self, params: MeanReversionParams | None = None):
        self.p = params or MeanReversionParams()

    def indicators(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.p
        h, l, c = bars["high"], bars["low"], bars["close"]
        out = pd.DataFrame(index=bars.index)
        out["atr"] = ind.atr(h, l, c, p.atr_period)
        out["adx"] = ind.adx(h, l, c, p.adx_period)
        ma = c.rolling(p.ma_period).mean()
        sd = c.rolling(p.ma_period).std()
        out["ma"] = ma
        out["z"] = (c - ma) / sd.replace(0, np.nan)
        return out

    def signals(self, bars: pd.DataFrame, feats: pd.DataFrame | None = None) -> pd.Series:
        p = self.p
        f = feats if feats is not None else self.indicators(bars)
        z = f["z"]

        # fade the stretch: too high -> short, too low -> long
        long_ok = z <= -p.z_entry
        short_ok = z >= p.z_entry

        if p.use_adx_gate:
            calm = f["adx"] <= p.adx_ceiling
            long_ok &= calm
            short_ok &= calm
        if not p.allow_shorts:
            short_ok &= False

        sig = pd.Series(0.0, index=bars.index)
        sig[long_ok.fillna(False)] = 1.0
        sig[short_ok.fillna(False)] = -1.0
        return sig
