"""15-min Opening Range Breakout (Strategy #1) - parameter optimizer with walk-forward validation.

Input CSV (5-min bars, regular hours, US/Eastern): timestamp,open,high,low,close
Usage: python orb_optimizer.py bars.csv        |  python orb_optimizer.py --synthetic
Results are in R (risk multiples). Costs are charged per trade in R.
"""
import sys, itertools, random
import pandas as pd, numpy as np

def trades(df, stop_mode, exit_mode, rr, trail_atr, cost_r=0.05, max_range_pct=None):
    out = []
    for day, d in df.groupby(df.index.date):
        d = d.between_time("09:30", "16:00")
        if len(d) < 20: continue
        orb = d.iloc[:3]                       # 9:30-9:45 = first 15 min (three 5m bars)
        hi, lo = orb.high.max(), orb.low.min()
        rng = hi - lo
        if rng <= 0 or (max_range_pct and rng / orb.open.iloc[0] > max_range_pct): continue
        side = entry = stop = None
        for t, b in d.iloc[3:].iterrows():
            if side is None:
                if b.close > hi: side, entry = 1, b.close
                elif b.close < lo: side, entry = -1, b.close
                else: continue
                stop = (lo if side == 1 else hi) if stop_mode == "opposite" else (lo + hi) / 2
                risk = abs(entry - stop)
                if risk <= 0: side = None; continue
                best = entry
                continue
            if side == 1:
                if b.low <= stop: out.append((day, (stop - entry) / risk - cost_r)); side = 0; break
                best = max(best, b.high)
                if exit_mode == "target" and b.high >= entry + rr * risk: out.append((day, rr - cost_r)); side = 0; break
                if exit_mode == "trail": stop = max(stop, best - trail_atr * rng)
            else:
                if b.high >= stop: out.append((day, (entry - stop) / risk - cost_r)); side = 0; break
                best = min(best, b.low)
                if exit_mode == "target" and b.low <= entry - rr * risk: out.append((day, rr - cost_r)); side = 0; break
                if exit_mode == "trail": stop = min(stop, best + trail_atr * rng)
        if side in (1, -1):                    # exit at close
            last = d.close.iloc[-1]; out.append((day, side * (last - entry) / risk - cost_r))
    return pd.Series({k: v for k, v in out})

def score(r):  # robust score: expectancy penalised by drawdown, needs enough trades
    if len(r) < 30: return -9
    dd = (r.cumsum().cummax() - r.cumsum()).max()
    return r.sum() / (1 + dd)

GRID = [dict(stop_mode=s, exit_mode=e, rr=rr, trail_atr=t)
        for s in ("opposite", "mid") for e in ("close", "target", "trail")
        for rr in (1, 2, 3) for t in (0.5, 1.0, 1.5)]

def walk_forward(df, train_months=12, test_months=3):
    months = sorted(set(df.index.to_period("M")))
    res = []
    for i in range(train_months, len(months) - test_months + 1, test_months):
        tr = df[(df.index.to_period("M") >= months[i-train_months]) & (df.index.to_period("M") < months[i])]
        te = df[(df.index.to_period("M") >= months[i]) & (df.index.to_period("M") < months[i+test_months-1] + 1)]
        best = max(GRID, key=lambda p: score(trades(tr, **p)))
        r = trades(te, **best); res.append((str(months[i]), best, r.sum(), len(r)))
    return res

def synthetic():
    idx = pd.bdate_range("2025-01-01", "2026-06-30"); rows = []; p = 400.0
    for d in idx:
        for k in range(78):
            t = d + pd.Timedelta(hours=9, minutes=30 + 5 * k); o = p; p = o * (1 + random.gauss(0, 0.0008))
            rows.append((t, o, max(o, p) * 1.0003, min(o, p) * 0.9997, p))
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"]).set_index("timestamp")

if __name__ == "__main__":
    df = synthetic() if "--synthetic" in sys.argv else pd.read_csv(sys.argv[1], parse_dates=["timestamp"]).set_index("timestamp")
    print("In-sample grid (top 5):")
    for p in sorted(GRID, key=lambda p: -score(trades(df, **p)))[:5]:
        r = trades(df, **p); print(p, f"R={r.sum():.1f} n={len(r)} win={(r>0).mean():.0%}")
    print("\nWalk-forward (choose on train, trade unseen test):")
    wf = walk_forward(df); [print(*x) for x in wf]
    print("Total out-of-sample R:", round(sum(x[2] for x in wf), 1))
