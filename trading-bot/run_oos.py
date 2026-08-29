"""OUT-OF-SAMPLE: 2025. Run ONCE.

Config locked from 2024 marginal effects BEFORE looking at 2025:
  tf=1h     most trades -> most statistical power
  ma=100    best median return AND best profitable-fraction of {20,50,100}
  z=2.0     {2.5} scored marginally better but on far fewer trades
  gate=off  ADX gate hurt in every slice (35% vs 21% profitable)
  stop=3.0  strongest monotone effect in the grid (51% vs 6% at 1.0)
  rr=1.0    middle of the favourable band, deliberately NOT the peak

The single best 2024 cell was rr=0.75 at +20.54%. It is not used. Picking
the maximum of 1,647 tested configurations is curve-fitting by definition.
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dataclasses import replace
import pandas as pd

from tbot.engine import run_backtest
from tbot.instruments import EURUSD
from tbot.risk import RiskConfig
from tbot.metrics import summarise, format_report
from tbot.strategies.mean_reversion import MeanReversion, MeanReversionParams

PARAMS = MeanReversionParams(ma_period=100, z_entry=2.0, use_adx_gate=False)
CFG = RiskConfig(risk_pct=0.01, atr_stop_mult=3.0, reward_risk=1.0)

TIERS = {
    "tight ECN (0.2p+$7/lot RT)": replace(EURUSD, typical_spread_pips=0.2, commission_per_lot=3.5),
    "typical   (1.2p, no comm)":  replace(EURUSD, typical_spread_pips=1.2, commission_per_lot=0.0),
    "wide      (1.8p, no comm)":  replace(EURUSD, typical_spread_pips=1.8, commission_per_lot=0.0),
    "ZERO COST (reference only)": replace(EURUSD, typical_spread_pips=0.0, commission_per_lot=0.0),
}

s = MeanReversion(PARAMS)
for year, label in [(2024, "IN-SAMPLE (tuned here)"), (2025, "OUT-OF-SAMPLE (first look)")]:
    bars = pd.read_pickle("data/EURUSD_1h.pkl")
    bars = bars[bars.index.year == year]
    feats = s.indicators(bars); sig = s.signals(bars, feats)
    print(f"\n{'='*78}\n{year}  {label}   bars={len(bars)}  signals={int((sig!=0).sum())}\n{'='*78}")
    print(f"{'cost tier':<28}{'net':>9}{'PF':>7}{'win%':>7}{'trades':>8}{'maxDD':>9}{'Sharpe':>8}")
    print("-"*78)
    for name, inst in TIERS.items():
        slip = 0.0 if "ZERO" in name else 0.5
        res = run_backtest(bars, sig, feats["atr"], inst, CFG, 10_000, slippage_pips=slip)
        m = summarise(res.equity, res.trades_frame(), 252*24)
        if m.get("n_trades", 0) == 0:
            print(f"{name:<28}  no trades"); continue
        print(f"{name:<28}{m['total_return']*100:8.2f}%{m['profit_factor']:7.2f}"
              f"{m['win_rate']*100:6.1f}%{m['n_trades']:8d}{m['max_drawdown']*100:8.2f}%"
              f"{m['sharpe']:8.2f}")
