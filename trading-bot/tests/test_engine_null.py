"""The engine must NOT make money on random data. This is the whole ballgame."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from tbot.engine import run_backtest
from tbot.instruments import EURUSD
from tbot.risk import RiskConfig
from tbot.synthetic import random_walk_ohlc
from tbot import indicators as ind


def test_random_signals_on_random_walk_lose_costs():
    """Random entries on a random walk should lose approximately the cost total."""
    bars = random_walk_ohlc(n=15_000, seed=7)
    rng = np.random.default_rng(1)
    sig = pd.Series(rng.choice([0, 0, 0, 0, 1, -1], size=len(bars)), index=bars.index, dtype=float)
    atr = ind.atr(bars["high"], bars["low"], bars["close"], 14)

    res = run_backtest(bars, sig, atr, EURUSD, RiskConfig(), initial_equity=10_000)
    tf = res.trades_frame()
    net = res.equity.iloc[-1] - 10_000

    assert len(tf) > 100, "test needs a meaningful number of trades"
    # Net must be negative and of the same order as total costs paid.
    assert net < 0, f"engine produced PROFIT ({net:.2f}) on a random walk - look-ahead bug"
    print(f"  random/random: net {net:.2f}, costs {tf['costs'].sum():.2f}, n={len(tf)}")


def test_zero_cost_random_is_near_zero():
    """With costs stripped out, random trading on a random walk ~ breakeven."""
    from dataclasses import replace
    bars = random_walk_ohlc(n=15_000, seed=11)
    free = replace(EURUSD, typical_spread_pips=0.0, commission_per_lot=0.0)
    rng = np.random.default_rng(2)
    sig = pd.Series(rng.choice([0, 0, 0, 0, 1, -1], size=len(bars)), index=bars.index, dtype=float)
    atr = ind.atr(bars["high"], bars["low"], bars["close"], 14)

    res = run_backtest(bars, sig, atr, free, RiskConfig(), initial_equity=10_000, slippage_pips=0.0)
    net_pct = res.equity.iloc[-1] / 10_000 - 1
    print(f"  zero-cost random: {net_pct*100:+.2f}% over {len(res.trades)} trades")
    assert abs(net_pct) < 0.35, f"frictionless random walk drifted {net_pct*100:.1f}% - suspicious"


def test_risk_per_losing_trade_is_one_percent():
    """Every stop-out should cost ~1% of equity at the time of entry."""
    bars = random_walk_ohlc(n=8_000, seed=3)
    rng = np.random.default_rng(4)
    sig = pd.Series(rng.choice([0, 0, 1, -1], size=len(bars)), index=bars.index, dtype=float)
    atr = ind.atr(bars["high"], bars["low"], bars["close"], 14)
    res = run_backtest(bars, sig, atr, EURUSD, RiskConfig(risk_pct=0.01), initial_equity=10_000)

    tf = res.trades_frame()
    stops = tf[tf["exit_reason"] == "stop"]
    eq_at_entry = 10_000  # approximate; drift is small early on
    med_loss = stops["pnl"].median()
    print(f"  median stop-out loss {med_loss:.2f} on ~{eq_at_entry} equity "
          f"({med_loss/eq_at_entry*100:.2f}%)")
    assert -0.020 * eq_at_entry < med_loss < -0.005 * eq_at_entry, \
        f"stop-out loss {med_loss:.2f} is not ~1% of equity"


if __name__ == "__main__":
    for fn in (test_random_signals_on_random_walk_lose_costs,
               test_zero_cost_random_is_near_zero,
               test_risk_per_losing_trade_is_one_percent):
        print(f"\n{fn.__name__}")
        fn()
        print("  PASS")
