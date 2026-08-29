"""How much real trend is needed before the edge survives costs?

This is the question that decides whether any of this is worth doing.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dataclasses import replace

from tbot.engine import run_backtest
from tbot.instruments import EURUSD
from tbot.risk import RiskConfig
from tbot.metrics import summarise
from tbot.strategies import TrendBreakout, TrendBreakoutParams
from tbot.synthetic import trending_ohlc

strat = TrendBreakout(TrendBreakoutParams())
cfg = RiskConfig()
free = replace(EURUSD, typical_spread_pips=0.0, commission_per_lot=0.0)

print(f"{'trend':>7} | {'net w/costs':>12} {'PF':>6} {'win%':>6} {'n':>5} "
      f"| {'net NO costs':>12} {'PF':>6} | {'edge eaten':>10}")
print("-"*86)

for strength in [0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.20]:
    rc, rf, pfc, pff, wr, nt = [], [], [], [], [], []
    for seed in range(6):
        bars = trending_ohlc(n=20_000, seed=seed, strength=strength, regime_len=500)
        feats = strat.indicators(bars); sig = strat.signals(bars, feats)

        r1 = run_backtest(bars, sig, feats["atr"], EURUSD, cfg, 10_000, slippage_pips=0.5)
        m1 = summarise(r1.equity, r1.trades_frame(), 252*24)
        r2 = run_backtest(bars, sig, feats["atr"], free, cfg, 10_000, slippage_pips=0.0)
        m2 = summarise(r2.equity, r2.trades_frame(), 252*24)

        if m1.get("n_trades", 0) > 20:
            rc.append(m1["total_return"]); pfc.append(m1["profit_factor"])
            wr.append(m1["win_rate"]); nt.append(m1["n_trades"])
            rf.append(m2["total_return"]); pff.append(m2["profit_factor"])

    if not rc:
        print(f"{strength:7.2f} |  too few trades"); continue
    avg = lambda x: sum(x)/len(x)
    eaten = avg(pff) - avg(pfc)
    print(f"{strength:7.2f} | {avg(rc)*100:11.1f}% {avg(pfc):6.2f} {avg(wr)*100:5.1f}% "
          f"{avg(nt):5.0f} | {avg(rf)*100:11.1f}% {avg(pff):6.2f} | {eaten:9.2f}")
