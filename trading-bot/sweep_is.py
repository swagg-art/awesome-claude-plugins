"""Parameter sensitivity, IN-SAMPLE 2024 only.

Reports the DISTRIBUTION, not the best cell. A strategy whose grid is
mostly negative with a couple of positive spikes has no edge - those
spikes are noise, and picking one is how curve-fitting happens.
"""
import sys, pathlib, itertools; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dataclasses import replace
import numpy as np, pandas as pd

from tbot.engine import run_backtest
from tbot.instruments import EURUSD
from tbot.risk import RiskConfig
from tbot.metrics import summarise
from tbot.strategies import TrendBreakout, TrendBreakoutParams

inst = replace(EURUSD, typical_spread_pips=1.2, commission_per_lot=0.0)
rows = []
for tf in ["1h", "4h"]:
    bars = pd.read_pickle(f"data/EURUSD_{tf}.pkl")
    bars = bars[bars.index.year == 2024]
    ppy = 252*24 if tf == "1h" else 252*6
    for dc, adxf, struct, shorts in itertools.product(
            [10, 20, 40, 60], [0.0, 20.0, 25.0], [True, False], [True, False]):
        p = TrendBreakoutParams(donchian_period=dc, adx_floor=adxf,
                                use_structure=struct, allow_shorts=shorts)
        s = TrendBreakout(p)
        feats = s.indicators(bars); sig = s.signals(bars, feats)
        for stop_m, rr in itertools.product([1.5, 2.0, 3.0], [1.0, 1.5, 2.0, 3.0]):
            cfg = RiskConfig(atr_stop_mult=stop_m, reward_risk=rr)
            res = run_backtest(bars, sig, feats["atr"], inst, cfg, 10_000, slippage_pips=0.5)
            m = summarise(res.equity, res.trades_frame(), ppy)
            if m.get("n_trades", 0) < 15:
                continue
            rows.append(dict(tf=tf, dc=dc, adx=adxf, struct=struct, shorts=shorts,
                             stop=stop_m, rr=rr, ret=m["total_return"],
                             pf=m["profit_factor"], n=m["n_trades"],
                             win=m["win_rate"], dd=m["max_drawdown"]))

df = pd.DataFrame(rows)
df.to_csv("sweep_is_2024.csv", index=False)
print(f"grid cells with >=15 trades: {len(df)}")
print(f"profitable cells           : {(df['ret']>0).sum()}  ({(df['ret']>0).mean()*100:.1f}%)")
print(f"cells with PF > 1.2        : {(df['pf']>1.2).sum()}")
print(f"median return              : {df['ret'].median()*100:+.2f}%")
print(f"median profit factor       : {df['pf'].median():.3f}")
print(f"best  return               : {df['ret'].max()*100:+.2f}%")
print(f"worst return               : {df['ret'].min()*100:+.2f}%")
print("\nTop 8 cells (IN-SAMPLE - these are candidates, NOT results):")
print(df.nlargest(8, "ret").to_string(index=False,
      formatters={"ret": lambda x: f"{x*100:+.2f}%", "win": lambda x: f"{x*100:.1f}%",
                  "dd": lambda x: f"{x*100:.1f}%", "pf": lambda x: f"{x:.2f}"}))
print("\nBy timeframe:")
print(df.groupby("tf")["ret"].describe()[["count","mean","50%","max"]].to_string())
print("\nBy shorts allowed:")
print(df.groupby("shorts")["ret"].agg(["count","mean","median"]).to_string())
