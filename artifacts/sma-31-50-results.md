# SMA 31/50 crossover backtest (daily, 2016-11-21 to 2026-11-20, Yahoo Finance)
Rules: fast SMA(31) vs slow SMA(50) on closes; signal at close, trade next open; 0.05% cost per side. Long-only = long when fast > slow else cash. Long/short = short when fast < slow. Script: sma_cross_backtest.py

| Market | Strategy | Total | CAGR | Max DD | Sharpe | Trades |
|---|---|---|---|---|---|---|
| QQQ | Buy & hold | +413% | 17.8% | -35.6% | 0.83 | - |
| QQQ | SMA long-only | +102% | 7.3% | -36.6% | 0.50 | 50 |
| QQQ | SMA long/short | -36% | -4.4% | -65.4% | -0.08 | 51 |
| SPY | Buy & hold | +213% | 12.1% | -34.1% | 0.72 | - |
| SPY | SMA long-only | +85% | 6.4% | -34.4% | 0.58 | 46 |
| SPY | SMA long/short | -9% | -1.0% | -53.0% | 0.04 | 47 |
| DIA | Buy & hold | +154% | 9.8% | -37.1% | 0.62 | - |
| DIA | SMA long-only | +24% | 2.2% | -32.7% | 0.25 | 51 |
| DIA | SMA long/short | -49% | -6.6% | -59.6% | -0.29 | 52 |

Not financial advice; one parameter pair, no taxes or slippage beyond cost, past results only.

## Added: 20/50 and 50/200 (same data, rules and costs)
Long-only (long when fast > slow, else cash) / long-short:
| Market | Pair | Long-only total / CAGR / maxDD / Sharpe | Long-short total / maxDD |
|---|---|---|---|
| QQQ | 20/50 | +153% / 9.8% / -30.3% / 0.66 | -4% / -45.5% |
| QQQ | 50/200 | +269% / 14.0% / -28.6% / 0.77 | +132% / -29.0% |
| SPY | 20/50 | +97% / 7.0% / -29.9% / 0.64 | +2% / -47.9% |
| SPY | 50/200 | +90% / 6.6% / -34.1% / 0.50 | +4% / -41.5% |
| DIA | 20/50 | +58% / 4.7% / -21.7% / 0.46 | -18% / -43.4% |
| DIA | 50/200 | +23% / 2.1% / -37.6% / 0.21 | -45% / -60.7% |
Buy & hold for reference: QQQ +413%, SPY +213%, DIA +154%. No pair beat buy & hold on return; 20/50 and QQQ 50/200 cut drawdown.
