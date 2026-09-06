# Backtest suite — GBPUSD M15 — 24915 bars

**Data:** `data/GBPUSD_M1_2020.csv`  
**Bars:** 24915, 2020-01-01 17:00:00 → 2020-12-31 16:45:00  
**Timeframe detected:** M15  
**Spread used:** 0.00015 (supplied)
**Contract size:** 100000.0  
**Starting equity:** 10,000.00

## Data warnings

- timestamps were out of order; sorted
- 60 duplicate timestamp(s) dropped
- resampled 372,997 bars to 24,915 at 15min

## Full sample

| strategy | trades | win% | PF | net | maxDD% | note |
|---|---|---|---|---|---|---|
| simple (threshold, fixed stops) | 614 | 28.5 | 0.734 | -240.37 | 2.44 | the original |
| confirmed (config default) | 374 | 24.6 | 0.946 | -40.74 | 1.14 | 1087 setups armed |
| confirmed, divergence-only arming | 269 | 23.4 | 0.808 | -126.15 | 2.52 | 826 setups armed |
| confirmed + EMA 50 | 126 | 20.6 | 0.584 | -185.68 | 2.13 | 472 filtered out |
| confirmed + EMA 100 | 98 | 25.5 | 0.735 | -90.49 | 1.28 | 547 filtered out |
| confirmed + EMA 200 | 127 | 27.6 | 1.071 | +21.43 | 0.88 | 518 filtered out |
| confirmed, long only | 240 | 25.4 | 1.014 | +6.47 | 0.62 | 336 filtered out |

## Walk forward (70/30 at bar 17440)

| variant | in trades | in net | out trades | out net |
|---|---|---|---|---|
| confirmed (config default) | 265 | -23.89 | 112 | -45.26 |
| confirmed, divergence-only | 192 | -146.29 | 78 | -2.83 |
| confirmed + EMA 100 | 64 | -28.96 | 34 | -57.80 |
| confirmed, long only | 164 | -2.80 | 75 | -9.10 |
| simple | 432 | -157.24 | 182 | -83.13 |

## Reading this

The out-of-sample column is the one that matters. A variant that
wins in sample and loses out of sample is fitted to the past.

Fill assumptions (all pessimistic where there was a choice) are
printed by `python backtest.py --explain`.
