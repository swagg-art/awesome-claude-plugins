"""In-sample run: 2024 only. 2025 is NOT touched here."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dataclasses import replace
import pandas as pd

from tbot.engine import run_backtest
from tbot.instruments import EURUSD
from tbot.risk import RiskConfig
from tbot.metrics import summarise
from tbot.strategies import TrendBreakout, TrendBreakoutParams

BARS_PER_YEAR = {"1h": 252*24, "4h": 252*6, "15min": 252*96}

COST_TIERS = {
    "tight ECN  (0.2p + $7/lot)": replace(EURUSD, typical_spread_pips=0.2, commission_per_lot=3.5),
    "typical    (1.2p + $0)":     replace(EURUSD, typical_spread_pips=1.2, commission_per_lot=0.0),
    "wide       (1.8p + $0)":     replace(EURUSD, typical_spread_pips=1.8, commission_per_lot=0.0),
    "ZERO COST  (reference)":     replace(EURUSD, typical_spread_pips=0.0, commission_per_lot=0.0),
}

def load(tf):
    df = pd.read_pickle(f"data/EURUSD_{tf}.pkl")
    return df[df.index.year == 2024]

strat = TrendBreakout(TrendBreakoutParams())
cfg = RiskConfig(risk_pct=0.01, atr_stop_mult=2.0, reward_risk=2.0)

for tf in ["1h", "4h"]:
    bars = load(tf)
    feats = strat.indicators(bars)
    sig = strat.signals(bars, feats)
    n_sig = int((sig != 0).sum())
    print(f"\n{'='*74}\n{tf}  IN-SAMPLE 2024   bars={len(bars)}  raw signals={n_sig}\n{'='*74}")
    print(f"{'cost tier':<28} {'net':>9} {'PF':>6} {'win%':>6} {'trades':>7} {'maxDD':>8} {'Sharpe':>7}")
    print("-"*74)
    for name, inst in COST_TIERS.items():
        slip = 0.0 if "ZERO" in name else 0.5
        res = run_backtest(bars, sig, feats["atr"], inst, cfg, 10_000, slippage_pips=slip)
        m = summarise(res.equity, res.trades_frame(), BARS_PER_YEAR[tf])
        if m.get("n_trades", 0) == 0:
            print(f"{name:<28}   no trades"); continue
        print(f"{name:<28} {m['total_return']*100:8.2f}% {m['profit_factor']:6.2f} "
              f"{m['win_rate']*100:5.1f}% {m['n_trades']:7d} {m['max_drawdown']*100:7.2f}% "
              f"{m['sharpe']:7.2f}")
