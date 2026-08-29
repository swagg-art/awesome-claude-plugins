"""Two-sided validation of strategy + engine on synthetic data."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tbot.engine import run_backtest
from tbot.instruments import EURUSD
from tbot.risk import RiskConfig
from tbot.metrics import summarise, format_report
from tbot.strategies import TrendBreakout, TrendBreakoutParams
from tbot.synthetic import random_walk_ohlc, trending_ohlc

strat = TrendBreakout(TrendBreakoutParams())
cfg = RiskConfig(risk_pct=0.01, atr_stop_mult=2.0, reward_risk=2.0)

def run(bars, label):
    feats = strat.indicators(bars)
    sig = strat.signals(bars, feats)
    res = run_backtest(bars, sig, feats["atr"], EURUSD, cfg,
                       initial_equity=10_000, slippage_pips=0.5)
    m = summarise(res.equity, res.trades_frame(), periods_per_year=252*24)
    print(f"\n=== {label} ===")
    print(format_report(m))
    return m

print("NULL CONTROL  - random walk, no exploitable structure.")
print("               A profit here means the code is lying.")
null_seeds = [1, 2, 3, 4, 5]
null_returns = []
for s in null_seeds:
    m = run(random_walk_ohlc(n=20_000, seed=s), f"random walk seed={s}")
    null_returns.append(m.get("total_return", 0))

print("\n\nPOSITIVE CONTROL - persistent trend regimes, a REAL edge exists.")
print("                   A loss here means the strategy cannot detect trends.")
pos_returns = []
for s in [1, 2, 3]:
    m = run(trending_ohlc(n=20_000, seed=s, strength=0.45), f"trending seed={s}")
    pos_returns.append(m.get("total_return", 0))

print("\n" + "="*58)
print(f"null    mean return: {sum(null_returns)/len(null_returns)*100:+7.2f}%  "
      f"(want negative - costs)")
print(f"trended mean return: {sum(pos_returns)/len(pos_returns)*100:+7.2f}%  "
      f"(want positive - edge survives costs)")
print("="*58)
