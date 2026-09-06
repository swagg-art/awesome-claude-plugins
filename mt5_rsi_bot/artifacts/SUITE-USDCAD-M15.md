# Backtest suite — USDCAD M15 — 71435 bars

**Data:** `data/USDCAD_M1_2023-2025.csv`  
**Bars:** 71435, 2023-01-01 18:00:00 → 2025-12-31 16:45:00  
**Timeframe detected:** M15  
**Spread used:** 0.00020 (supplied)
**Contract size:** 100000.0  
**Starting equity:** 10,000.00

## Data warnings

- timestamps were out of order; sorted
- 179 duplicate timestamp(s) dropped
- resampled 1,064,155 bars to 71,435 at 15min

## Full sample

| strategy | trades | win% | PF | net | maxDD% | note |
|---|---|---|---|---|---|---|
| simple (threshold, fixed stops) | 1087 | 31.4 | 0.847 | -251.27 | 2.72 | the original |
| confirmed (config default) | 707 | 20.2 | 0.661 | -365.33 | 3.82 | 2018 setups armed |
| confirmed, divergence-only arming | 603 | 18.2 | 0.552 | -455.47 | 4.76 | 1786 setups armed |
| confirmed + EMA 50 | 235 | 23.4 | 0.809 | -94.83 | 1.14 | 801 filtered out |
| confirmed + EMA 100 | 227 | 22.0 | 0.659 | -164.14 | 1.68 | 1135 filtered out |
| confirmed + EMA 200 | 271 | 22.9 | 0.648 | -177.53 | 1.93 | 1100 filtered out |
| confirmed, long only | 529 | 21.6 | 0.819 | -138.94 | 1.64 | 598 filtered out |

## Walk forward (70/30 at bar 50004)

| variant | in trades | in net | out trades | out net |
|---|---|---|---|---|
| confirmed (config default) | 427 | -199.60 | 282 | -175.37 |
| confirmed, divergence-only | 377 | -303.79 | 227 | -159.58 |
| confirmed + EMA 100 | 147 | -137.24 | 83 | -31.39 |
| confirmed, long only | 342 | -36.71 | 186 | -107.37 |
| simple | 790 | -135.54 | 297 | -115.72 |

## Reading this

The out-of-sample column is the one that matters. A variant that
wins in sample and loses out of sample is fitted to the past.

Fill assumptions (all pessimistic where there was a choice) are
printed by `python backtest.py --explain`.
